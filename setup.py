try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
    
requirements = [
                'scp',
                'scipy',
                'numpy>=1.9',
                'paramiko>=2.0',
                'nose>=1.0'
               ]

setup(
    name = 'StemLab',
    version = '0.1',
    description = 'Fork of PyRPL',
    packages = [
                'stemlab',
                ],
    install_requires = requirements,
    license = 'GPLv3',
    long_description=open('README.txt').read(),
)
