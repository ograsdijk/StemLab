###############################################################################
#    pyrpl - DSP servo controller for quantum optics with the RedPitaya
#    Copyright (C) 2014-2016  Leonhard Neuhaus  (neuhaus@spectro.jussieu.fr)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
###############################################################################

from . import stemlab_client
from . import hardware_modules as rp
from .sshshell import SshShell
from .pyrpl_utils import get_unique_name_list_from_class_list

import logging
import os
import random
import socket
from time import sleep
import numpy as np

from paramiko import SSHException
from scp import SCPClient, SCPException
from collections import OrderedDict

# default parameters for redpitaya object creation
defaultparameters = dict(
    hostname='172.28.170.46', #'192.168.1.100', # the ip or hostname of the board, '' triggers gui
    port=2222,  # port for PyRPL datacommunication
    sshport=22,  # port of ssh server - default 22
    user='root',
    password='root',
    delay=0.05,  # delay between ssh commands - console is too slow otherwise
    autostart=True,  # autostart the client?
    reloadserver=False,  # reinstall the server at startup if not necessary?
    reloadfpga=True,  # reload the fpga bitfile at startup?
    serverbinfilename='fpga.bin',  # name of the binfile on the server
    serverdirname = "//opt//pyrpl//",  # server directory for server app and bitfile
    leds_off=True,  # turn off all GPIO lets at startup (improves analog performance)
    frequency_correction=1.0,  # actual FPGA frequency is 125 MHz * frequency_correction
    timeout=1,  # timeout in seconds for ssh communication
    monitor_server_name='monitor_server',  # name of the server program on redpitaya
    silence_env=False)  # suppress all environment variables that may override the configuration?


class StemLab(object):
    cls_modules = [rp.HK, rp.Scope, rp.Sampler, rp.Asg0, rp.Asg1] + \
                  [rp.Pwm] * 2 + [rp.Iq] * 3 + [rp.Pid] * 3 + [rp.Trig] + [ rp.IIR]
    def __init__(self, **kwargs):
        """ this class provides the basic interface to the StemLab board

        The constructor installs and starts the communication interface on the StemLab
        at 'hostname' that allows remote control and readout

        Possible keyword arguments and their defaults are:
            hostname='192.168.1.100', # the ip or hostname of the board
            port=2222,  # port for PyRPL datacommunication
            sshport=22,  # port of ssh server - default 22
            user='root',
            password='root',
            delay=0.05,  # delay between ssh commands - console is too slow otherwise
            autostart=True,  # autostart the client?
            reloadserver=False,  # reinstall the server at startup if not necessary?
            reloadfpga=True,  # reload the fpga bitfile at startup?
            filename='fpga//red_pitaya.bin',  # name of the bitfile for the fpga, None is default file
            serverbinfilename='fpga.bin',  # name of the binfile on the server
            serverdirname = "//opt//pyrpl//",  # server directory for server app and bitfile
            leds_off=True,  # turn off all GPIO lets at startup (improves analog performance)
            frequency_correction=1.0,  # actual FPGA frequency is 125 MHz * frequency_correction
            timeout=3,  # timeout in seconds for ssh communication
            monitor_server_name='monitor_server',  # name of the server program on redpitaya
            silence_env=False)  # suppress all environment variables that may override the configuration?
        """
        self.logger = logging.getLogger(name=__name__)
        self.parameters = defaultparameters
        self.parameters.update(kwargs)

        self.frequency_correction = self.parameters['frequency_correction']

        self.client = None  # client class
        self._slaves = []  # slave interfaces to same redpitaya
        self.modules = OrderedDict()  # all submodules

        # connect to the redpitaya board
        self.start_ssh()
        # start other stuff
        if self.parameters['reloadfpga']:  # flash fpga
            self.update_fpga()
        if self.parameters['reloadserver']:  # reinstall server app
            self.installserver()
        if self.parameters['autostart']:  # start client
            self.start()
        self.logger.info('Successfully connected to StemLab with hostname '
                         '%s.'%self.ssh.hostname)
        self.parent = self


    def start_ssh(self, attempt=0):
        """
        Extablishes an ssh connection to the StemLab board

        returns True if a successful connection has been established
        """
        try:
            # start ssh connection
            self.ssh = SshShell(hostname=self.parameters['hostname'],
                                sshport=self.parameters['sshport'],
                                user=self.parameters['user'],
                                password=self.parameters['password'],
                                delay=self.parameters['delay'],
                                timeout=self.parameters['timeout'])
            # test ssh connection for exceptions
            self.ssh.ask()
        except BaseException as e:  # connection problem
            if attempt < 3:
                # try to connect up to 3 times
                return self.start_ssh(attempt=attempt+1)
            else:  # even multiple attempts did not work
                raise ExpectedPyrplError(
                    "\nCould not connect to the Red Pitaya device with "
                    "the following parameters: \n\n"
                    "\thostname: %s\n"
                    "\tssh port: %s\n"
                    "\tusername: %s\n"
                    "\tpassword: ****\n\n"
                    "Please confirm that the device is reachable by typing "
                    "its hostname/ip address into a web browser and "
                    "checking that a page is displayed. \n\n"
                    "Error message: %s" % (self.parameters["hostname"],
                                           self.parameters["sshport"],
                                           self.parameters["user"],
                                           e))
        else:
            # everything went well, connection is established
            # also establish scp connection
            self.ssh.startscp()
            return True

    def switch_led(self, gpiopin=0, state=False):
        self.ssh.ask("echo " + str(gpiopin) + " > /sys/class/gpio/export")
        sleep(self.parameters['delay'])
        self.ssh.ask(
            "echo out > /sys/class/gpio/gpio" +
            str(gpiopin) +
            "/direction")
        sleep(self.parameters['delay'])
        if state:
            state = "1"
        else:
            state = "0"
        self.ssh.ask("echo " + state + " > /sys/class/gpio/gpio" +
            str(gpiopin) + "/value")
        sleep(self.parameters['delay'])

    def update_fpga(self, filename=None):
        if filename is None:
            try:
                source = self.parameters['filename']
            except KeyError:
                source = None
        self.end()
        sleep(self.parameters['delay'])
        self.ssh.ask('rw')
        sleep(self.parameters['delay'])
        self.ssh.ask('mkdir ' + self.parameters['serverdirname'])
        sleep(self.parameters['delay'])
        if source is None or not os.path.isfile(source):
            if source is not None:
                self.logger.warning('Desired bitfile "%s" does not exist. Using default file.',
                                    source)
            source = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'fpga', 'red_pitaya.bin')
        if not os.path.isfile(source):
            raise IOError("Wrong filename",
              "The fpga bitfile was not found at the expected location. Try passing the arguments "
              "dirname=\"c://github//pyrpl//pyrpl//\" adapted to your installation directory of pyrpl "
              "and filename=\"red_pitaya.bin\"! Current dirname: "
              + self.parameters['dirname'] +
              " current filename: "+self.parameters['filename'])
        for i in range(3):
            try:
                self.ssh.scp.put(source,
                             os.path.join(self.parameters['serverdirname'],
                                          self.parameters['serverbinfilename']))
            except (SCPException, SSHException):
                # try again before failing
                self.start_ssh()
                sleep(self.parameters['delay'])
            else:
                break
        # kill all other servers to prevent reading while fpga is flashed
        self.end()
        self.ssh.ask('killall nginx')
        self.ssh.ask('systemctl stop stemlab_nginx') # for 0.94 and higher
        self.ssh.ask('cat '
                 + os.path.join(self.parameters['serverdirname'], self.parameters['serverbinfilename'])
                 + ' > //dev//xdevcfg')
        sleep(self.parameters['delay'])
        self.ssh.ask('rm -f '+ os.path.join(self.parameters['serverdirname'], self.parameters['serverbinfilename']))
        self.ssh.ask("nginx -p //opt//www//")
        self.ssh.ask('systemctl start stemlab_nginx') # for 0.94 and higher #needs test
        sleep(self.parameters['delay'])
        self.ssh.ask('ro')

    def fpgarecentlyflashed(self):
        self.ssh.ask()
        result =self.ssh.ask("echo $(($(date +%s) - $(date +%s -r \""
        + os.path.join(self.parameters['serverdirname'], self.parameters['serverbinfilename']) +"\")))")
        age = None
        for line in result.split('\n'):
            try:
                age = int(line.strip())
            except:
                pass
            else:
                break
        if not age:
            self.logger.debug("Could not retrieve bitfile age from: %s",
                            result)
            return False
        elif age > 10:
            self.logger.debug("Found expired bitfile. Age: %s", age)
            return False
        else:
            self.logger.debug("Found recent bitfile. Age: %s", age)
            return True

    def installserver(self):
        self.endserver()
        sleep(self.parameters['delay'])
        self.ssh.ask('rw')
        sleep(self.parameters['delay'])
        self.ssh.ask('mkdir ' + self.parameters['serverdirname'])
        sleep(self.parameters['delay'])
        self.ssh.ask("cd " + self.parameters['serverdirname'])
        #try both versions
        for serverfile in ['monitor_server','monitor_server_0.95']:
            sleep(self.parameters['delay'])
            try:
                self.ssh.scp.put(
                    os.path.join(os.path.abspath(os.path.dirname(__file__)), 'monitor_server', serverfile),
                    self.parameters['serverdirname'] + self.parameters['monitor_server_name'])
            except (SCPException, SSHException):
                self.logger.exception("Upload error. Try again after rebooting your StemLab..")
            sleep(self.parameters['delay'])
            self.ssh.ask('chmod 755 ./'+self.parameters['monitor_server_name'])
            sleep(self.parameters['delay'])
            self.ssh.ask('ro')
            result = self.ssh.ask("./"+self.parameters['monitor_server_name']+" "+ str(self.parameters['port']))
            sleep(self.parameters['delay'])
            result += self.ssh.ask()
            if not "sh" in result:
                self.logger.debug("Server application started on port %d",
                              self.parameters['port'])
                return self.parameters['port']
            else: # means we tried the wrong binary version. make sure server is not running and try again with next file
                self.endserver()

        #try once more on a different port
        if self.parameters['port'] == self.parameters['defaultport']:
            self.parameters['port'] = random.randint(self.parameters['defaultport'],50000)
            self.logger.warning("Problems to start the server application. Trying again with a different port number %d",self.parameters['port'])
            return self.installserver()

        self.logger.error("Server application could not be started. Try to recompile monitor_server on your StemLab (see manual). ")
        return None

    def startserver(self):
        self.endserver()
        sleep(self.parameters['delay'])
        if self.fpgarecentlyflashed():
            self.logger.info("FPGA is being flashed. Please wait for 2 "
                            "seconds.")
            sleep(2.0)
        result = self.ssh.ask(self.parameters['serverdirname']+"/"+self.parameters['monitor_server_name']
                          +" "+ str(self.parameters['port']))
        if not "sh" in result: # sh in result means we tried the wrong binary version
            self.logger.debug("Server application started on port %d",
                              self.parameters['port'])
            self._serverrunning = True
            return self.parameters['port']
        #something went wrong
        return self.installserver()

    def endserver(self):
        try:
            self.ssh.ask('\x03') #exit running server application
        except:
            self.logger.exception("Server not responding...")
        if 'pitaya' in self.ssh.ask():
            self.logger.debug('>') # formerly 'console ready'
        sleep(self.parameters['delay'])
        # make sure no other monitor_server blocks the port
        self.ssh.ask('killall ' + self.parameters['monitor_server_name'])
        self._serverrunning = False

    def endclient(self):
        del self.client
        self.client = None

    def start(self):
        if self.parameters['leds_off']:
            self.switch_led(gpiopin=0, state=False)
            self.switch_led(gpiopin=7, state=False)
        self.startserver()
        sleep(self.parameters['delay'])
        self.startclient()

    def end(self):
        self.endserver()
        self.endclient()

    def end_ssh(self):
        self.ssh.channel.close()

    def end_all(self):
        self.end()
        self.end_ssh()

    def restart(self):
        self.end()
        self.start()

    def restartserver(self, port=None):
        """restart the server. usually executed when client encounters an error"""
        if port is not None:
            if port < 0: #code to try a random port
                self.parameters['port'] = random.randint(2223,50000)
            else:
                self.parameters['port'] = port
        return self.startserver()

    def startclient(self):
        self.client = stemlab_client.MonitorClient(
            self.parameters['hostname'], self.parameters['port'], restartserver=self.restartserver)
        self.makemodules()

    def startdummyclient(self):
        self.client = stemlab_client.DummyClient()
        self.makemodules()

    def makemodule(self, name, cls):
        module = cls(self, name)
        setattr(self, name, module)
        self.modules[name] = module

    def makemodules(self):
        """
        Automatically generates modules from the list StemLab.cls_modules
        """
        names = get_unique_name_list_from_class_list(self.cls_modules)
        for cls, name in zip(self.cls_modules, names):
            self.makemodule(name, cls)

    def make_a_slave(self, port=None, monitor_server_name=None, gui=False):
        if port is None:
            port = self.parameters['port'] + len(self._slaves)*10 + 1
        if monitor_server_name is None:
            monitor_server_name = self.parameters['monitor_server_name'] + str(port)
        slaveparameters = dict(self.parameters)
        slaveparameters.update(dict(
                         port=port,
                         autostart=True,
                         reloadfpga=False,
                         reloadserver=False,
                         monitor_server_name=monitor_server_name,
                         silence_env=True))
        r = StemLab(**slaveparameters) #gui=gui)
        r._master = self
        self._slaves.append(r)
        return r
