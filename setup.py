from setuptools import setup
import os

# path to the directory that contains the setup.py script
SETUP_PATH = os.path.dirname(os.path.abspath(__file__))

requirements = [
                'scp',
                'scipy',
                'numpy>=1.9',
                'paramiko>=2.0',
                'nose>=1.0'
               ]

def find_packages():
    """
    Simple function to find all modules under the current folder.
    """
    modules = []
    for dirpath, _, filenames in os.walk(os.path.join(SETUP_PATH, "stemlab")):
        if "__init__.py" in filenames:
            modules.append(os.path.relpath(dirpath, SETUP_PATH))
    return [module.replace(os.sep, ".") for module in modules]

print(find_packages())

setup(
    name = 'StemLab',
    version = '0.1',
    description = 'Fork of PyRPL',
    install_requires = requirements,
    packages=find_packages(), #['pyrpl'],
    package_data={'stemlab': ['fpga/*',
                          'monitor_server/*']},
    license = 'GPLv3',
    long_description=open('README.txt').read(),
)
