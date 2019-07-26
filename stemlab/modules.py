"""
Modules are the basic building blocks of Pyrpl.

The internal structure of the FPGA is made of individual modules, each
performing a well defined task. Each of these FPGA modules are represented
in python by a :obj:`HardwareModule`.

Higher-level operations, for instance those that need a coordinated
operation of several HardwareModules is performed by a SoftwareModule,
defined in a class derived from :obj:`Module`.

Thus, all modules (both :obj:`HardwareModule` and Software modules inherit
from :obj:`Module` which gives them basic capabilities such as displaying
their attributes in the GUI having their state load and saved in the config
file.
"""

from .attributes import BaseAttribute, ModuleAttribute
from .pyrpl_utils import DuplicateFilter, unique_list

import logging
import numpy as np
from six import with_metaclass
from collections import OrderedDict

class ModuleMetaClass(type):
    """
    Generate Module classes with two features:
    - __new__ lets attributes know what name they are referred to in the
    class that contains them.
    - __new__ also lists all the submodules. This info will be used when
    instantiating submodules at module instanciation time.
    - __init__ auto-generates the function setup() and its docstring """
    def __init__(self, classname, bases, classDict):
        """
        Magic to retrieve the name of the attributes in the attributes
        themselves.
        see http://code.activestate.com/recipes/577426-auto-named-decriptors/
        Iterate through the new class' __dict__ and update the .name of all
        recognised BaseAttribute.

        + list all submodules attributes

        formerly __init__
        1. Takes care of adding all submodules attributes to the list
        self._module_attributes

        2. Takes care of creating 'setup(**kwds)' function of the module.
        The setup function executes set_attributes(**kwds) and then _setup().

        We cannot use normal inheritance because we want a customized
        docstring for each module. The docstring is created here by
        concatenating the module's _setup docstring and individual
        setup_attribute docstrings.
        """
        if classname == 'ModuleContainer':
            pass

        # 0. make all attributes aware of their name in the class containing them
        for name, attr in self.__dict__.items():
            if isinstance(attr, BaseAttribute):
                attr.name = name
        # 1a. prepare _setup_attributes etc.
        _setup_attributes, _module_attributes = [], []

        for base in reversed(bases):  # append all base class _setup_attributes
            try: _setup_attributes += base._setup_attributes
            except AttributeError: pass
            try: _module_attributes += base._module_attributes
            except AttributeError: pass
        _setup_attributes += self._setup_attributes
        # 1b. make a list of _module_attributes and add _module_attributes to _setup_attributes
        for name, attr in self.__dict__.items():
            if isinstance(attr, ModuleAttribute):
                _module_attributes.append(name)
        self._module_attributes = unique_list(_module_attributes)
        # 1c. add _module_attributes to _setup_attributes if the submodule has _setup_attributes
        for name in self._module_attributes:
            attr = getattr(self, name)
            if True:  #len(attr.module_cls._setup_attributes) > 0:
                _setup_attributes.append(name)
        #1d. Set the unique list of _setup_attributes
        self._setup_attributes = unique_list(_setup_attributes)
        # 2. create setup(**kwds)
        if "setup" not in classDict:
            # a. generate a setup function
            def setup(self, **kwds):
                self._setup_ongoing = True
                try:
                    # user can redefine any setup_attribute through kwds
                    for key in self._setup_attributes:
                        if key in kwds:
                            value = kwds.pop(key)
                            setattr(self, key, value)
                    if len(kwds) > 0:
                        self._logger.warning(
                            "Trying to load attribute %s of module %s that "
                            "are invalid setup_attributes.",
                            sorted(kwds.keys())[0], self.name)
                    if hasattr(self, '_setup'):
                        self._setup()
                finally:
                    self._setup_ongoing = False
            # b. place the new setup function in the module class
            self.setup = setup
        # 3. if setup has no docstring, then make one
        self.make_setup_docstring(classDict)
        # 4. make the new class
        #return super(ModuleMetaClass, cls).__new__(cls, classname, bases, classDict)

    #@classmethod
    def make_setup_docstring(self, classDict):
        """
        Returns a docstring for the function 'setup' that is composed of:
          - the '_setup' docstring
          - the list of all setup_attributes docstrings
        """
        # get initial docstring (python 2 and python 3 syntax)
        try: doc = self._setup.__doc__ + '\n'
        except:
            try: doc = self._setup.__func__.__doc__ + '\n'
            except: doc = ""
        doc += "attributes\n=========="
        for attr_name in self._setup_attributes:
            attr = getattr(self, attr_name)
            doc += "\n  " + attr_name + ": " + attr.__doc__
        setup = self.setup
        # docstring syntax differs between python versions. Python 2:
        if hasattr(setup, "__func__"):
            setup.__func__.__doc__ = doc
        # ... python 3
        elif hasattr(setup, '__doc__'):
            setup.__doc__ = doc


class DoSetup(object):
    """
    A context manager that allows to nicely write Module setup functions.

    Usage example in :py:meth:`Module._setup()`::

        def _setup(self):
            # _setup_ongoing is False by default
            assert self._setup_ongoing == False
            with self.do_setup:
                # now _setup_ongoing is True
                assert self._setup_ongoing == True
                # do stuff that might fail
                raise BaseException()
            # even if _setup fails, _setup_ongoing is False afterwards or in
            # the next call to _setup()
            assert self._setup_ongoing == False
    """
    def __init__(self, parent):
        self.parent = parent

    def __enter__(self):
        self.parent._setup_ongoing = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.parent._setup_ongoing = False
        if exc_type is not None:
            self.parent._logger.warning("Exception %s was raised while "
                                        "_setup_ongoing was True: %s, %s",
                                        exc_type, exc_val, exc_tb)


class Module(with_metaclass(ModuleMetaClass, object)):
    # The Syntax for defining a metaclass changed from Python 2 to 3.
    # with_metaclass is compatible with both versions and roughly does this:
    # def with_metaclass(meta, *bases):
    #     """Create a base class with a metaclass."""
    #     return meta("NewBase", bases, {})
    # Specifically, ModuleMetaClass ensures that attributes have automatically
    # their internal name set properly upon module creation.
    """
    A module is a component of pyrpl doing a specific task.

    Module is the base class for instruments such as the
    Scope/Lockbox/NetworkAnalyzer. A module can have a widget to build a
    graphical user interface on top of it.
    It is composed of attributes (see attributes.py) whose values represent
    the current state of the module (more precisely, the state is defined
    by the value of all attributes in _setup_attributes)
    The module can be slaved or freed by a user or another module. When the
    module is freed, it goes back to the state immediately before being
    slaved. To make sure the module is freed, use the syntax::

        with pyrpl.mod_mag.pop('owner') as mod:
            mod.do_something()
            mod.do_something_else()

    Attributes:
        `get_setup_attributes()`: returns a dict with the current values of
            the setup attributes
        ``set_setup_attributes(**kwds)``: sets the provided setup_attributes
            (setup is not called)
        `save_state(name)`: saves the current 'state' (using
            get_setup_attribute) into the config file
        `load_state(name)`: loads the state 'name' from the config file (setup
            is not called by default)
        `erase_state(name)`: erases state 'name' from config file
        `create_widget()`: returns a widget according to widget_class
        ``setup(**kwds)``: first, performs :code:`set_setup_attributes(**kwds)`,
            then calls _setup() to set the module ready for acquisition. This
            method is automatically created by ModuleMetaClass and it combines the
            docstring of individual setup_attributes with the docstring of _setup()
        `free()`: sets the module owner to None, and brings the module back the
            state before it was slaved equivalent to module.owner = None)
        `get_yml(state=None)`: get the yml code representing the state "state'
            or the current state if state is None
        `set_yml(yml_content, state=None)`: sets the state "state" with the
            content of yml_content. If state is None, the state is directly loaded
            into the module.
        `name`: attributed based on name at instance creation
            (also used as a section key in the config file)
        `states (list)`: the list of states available in the config file
        `owner (string)`: a module can be owned (reserved) by a user or another
            module. The module is free if and only if owner is None
        `pyrpl` (:obj:`Pyrpl`): recursively looks through parent modules until it
            reaches the Pyrpl instance

    Class attributes to be implemented in derived class:

    - all individual attributes (instances of BaseAttribute)
    - _setup_attributes: attribute names that are touched by setup(**kwds)/
      saved/restored upon module creation

    Methods to implement in derived class:

    - _setup(): sets the module ready for acquisition/output with the
      current attribute's values. The metaclass of the module autogenerates a
      function like this::

          def setup(self, **kwds):
              \"\"\"
              _ docstring is the result of the following pseudocode: _
              print(DOCSTRING_OF_FUNCTION("_setup"))
              for attribute in self.setup_attributes:
                  print(DOCSTRING_OF_ATTRIBUTE(attribute))
              \"\"\"
              self.set_setup_attributes(kwds)
              return self._setup()

    - _ownership_changed(old, new): this function is called when the module
      owner changes it can be used to stop the acquisition for instance.
    """

    # attributes listed here will be saved in the config file everytime they
    # are updated.
    _setup_attributes = []

    # This flag is used to desactivate callback during setup
    _setup_ongoing = False

    # internal memory for owner of the module (to avoid conflicts)
    _owner = None

    # name of the module, metaclass automatically assigns one per instance
    name = None

    def __init__(self, parent, name=None):
        """
        Creates a module with given name. If name is None, cls.name is
        assigned by the metaclass.

        Parent is either
          - a pyrpl instance: config file entry is in
            (self.__class__.name + 's').(self.name)
          - or another SoftwareModule: config file entry is in
            (parent_entry).(self.__class__.name + 's').(self.name)
        """
        if name is not None:
            self.name = name
        self.do_setup = DoSetup(self)  # ContextManager for _setup_ongoing

        self._logger = logging.getLogger(name=__name__)
        self._logger.addFilter(DuplicateFilter())
        # create the signal launcher object from its class
        self.parent = parent
        # instantiate modules associated with _module_attribute by calling their getter
        for submodule in self._module_attributes:
            getattr(self, submodule)
        # custom module initialization hook
        # self._init_module()

    def _init_module(self):
        """
        To implement in child class if needed.
        """
        self._logger.warning("Function _init_module is obsolete and will be "
                             "removed soon. Please migrate the corresponding "
                             "code to __init__.")
    @property
    def _modules(self):
        return dict([(key, getattr(self, key)) for key in
                     self._module_attributes])

    def get_setup_attributes(self):
        """
        Returns a dict with the current values of the setup attributes.

        Recursively calls get_setup_attributes for sub_modules and assembles
        a hierarchical dictionary.

        Returns:
            dict: contains setup_attributes and their current values.
        """
        self._logger.warning("get_setup_attributes is deprecated. Use property setup_attributes instead. ")
        return self.setup_attributes

    @property
    def setup_attributes(self):
        """
        :return: a dict with the current values of the setup attributes.
        Recursively collects setup_attributes for sub_modules.
        """
        kwds = OrderedDict()
        for attr in self._setup_attributes:
            val = getattr(self, attr)
            if attr in self._modules:
                val = val.setup_attributes
            kwds[attr] = val
        return kwds

    def set_setup_attributes(self, **kwds):
        """
        Sets the values of the setup attributes. Without calling any callbacks
        """
        self._logger.warning("set_setup_attributes is deprecated. Use property setup_attributes instead. ")
        self.setup_attributes = kwds

    @setup_attributes.setter
    def setup_attributes(self, kwds):
        """
        Sets the values of the setup attributes.
        """
        self.setup(**kwds)

    def free(self):
        """
        Change ownership to None
        """
        self.owner = None

    def _setup(self):
        """
        Sets the module up for acquisition with the current setup attribute
        values.
        """
        pass

    def help(self, register=''):
        return "Please refer to the docstring of the function setup() or " \
               "to the manual for further help! "

    @property
    def owner(self):
        return self._owner

    @owner.setter
    def owner(self, val):
        """
        Changing module ownership automagically:
         - changes the visibility of the module_widget in the gui
         - re-setups the module with the module attributes in the config-file
           if new ownership is None
        """
        old = self.owner
        self._owner = val
        if val is None:
            self._autosave_active = True
        else:
            # deactivate autosave for slave modules
            self._autosave_active = False
        self._ownership_changed(old, val)
        if val is None:
            self._load_setup_attributes()
            # self.set_setup_attributes(**self.c._dict)
            # using the same dict will create a reference (&id) in the
            # config file for submodules --> That is probably a bug that
            # could be solved by making a copy of the dict somewhere in
            # memory.py, but on the other hand we are not supposed to use
            # anything but the public API of memory.py
        self._signal_launcher.change_ownership.emit()

    def _ownership_changed(self, old, new):
        pass

    def __enter__(self):
        """
        This function is executed in the context manager construct with
        ... as ... :
        """
        return self

    def __exit__(self, type, val, traceback):
        """
        To make sure the module will be freed afterwards, use the context
         manager construct:
        with pyrpl.module_manager.pop('owner') as mod:
            mod.do_something()
        # module automatically freed at this point

        The free operation is performed in this function
        see http://stackoverflow.com/questions/1369526/what-is-the-python-keyword-with-used-for
        """
        self.owner = None

    def _clear(self):
        """
        Kill timers and free resources for this module and all submodules.
        """
        for sub in self._modules:
            getattr(self, sub)._clear()


class HardwareModule(Module):
    """
    Module that directly maps a FPGA module. In addition to BaseModule's
    requirements, HardwareModule classes must have the following class
    attributes:

    - addr_base (int): the base address of the module, such as 0x40300000
    """

    parent = None  # parent will be redpitaya instance

    def __init__(self, parent, name=None):
        """ Creates the prototype of a RedPitaya Module interface

        if no name provided, will use cls.name
        """
        self._client = parent.client
        self._addr_base = self.addr_base
        self._rp = parent
        super(HardwareModule, self).__init__(parent, name=name)
        self.__doc__ = "Available registers: \r\n\r\n" + self.help()

    def _ownership_changed(self, old, new):
        """
        This hook is there to make sure any ongoing measurement is stopped when
        the module gets slaved

        old: name of old owner (eventually None)
        new: name of new owner (eventually None)
        """
        pass

    @property
    def _frequency_correction(self):
        """
        factor to manually compensate 125 MHz oscillator frequency error
        real_frequency = 125 MHz * _frequency_correction
        """
        try:
            return self._rp.frequency_correction
        except AttributeError:
            self._logger.warning("Warning: Parent of %s has no attribute "
                                 "'frequency_correction'. ", self.name)
            return 1.0

    def _reads(self, addr, length):
        return self._client.reads(self._addr_base + addr, length)

    def _writes(self, addr, values):
        self._client.writes(self._addr_base + addr, values)

    def _read(self, addr):
        return int(self._reads(addr, 1)[0])

    def _write(self, addr, value):
        self._writes(addr, [int(value)])

    def _to_pyint(self, v, bitlength=14):
        v = v & (2 ** bitlength - 1)
        if v >> (bitlength - 1):
            v = v - 2 ** bitlength
        return int(v)

    def _from_pyint(self, v, bitlength=14):
        v = int(v)
        if v < 0:
            v = v + 2 ** bitlength
        v = (v & (2 ** bitlength - 1))
        return np.uint32(v)

class SignalModule(Module):
    """ any module that can be passed as an input to another module"""
    def signal(self):
        return self.name
