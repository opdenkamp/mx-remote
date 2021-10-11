"""Setup for mx-remote python package."""
from os import path

from setuptools import find_packages, setup

THIS_DIRECTORY = path.abspath(path.dirname(__file__))
with open(path.join(THIS_DIRECTORY, 'README.md'), encoding='utf-8') as f:
    LONG_DESCRIPTION = f.read()

VERSION = {}
# pylint: disable=exec-used
with open(path.join(THIS_DIRECTORY, "mx_remote/const.py")) as fp:
    exec(fp.read(), VERSION)

REQUIRES = [
    'aiohttp>=3.6.2'
]

setup(
    name='mx_remote',
    description='Library for interfacing with Pulse-Eight devices',
    version=VERSION['__version__'],
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    download_url='https://github.com/opdenkamp/mx-remote/archive/{}.zip'.format(VERSION['__version__']),
    url='https://opdenkamp.eu/',
    author='Lars Op den Kamp',
    author_email='lars@opdenkamp.eu',
    license='GPL2',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',
        'Topic :: System :: Hardware :: Hardware Drivers',
        'License :: OSI Approved :: GPL2 License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ],
    packages=find_packages(),
    install_requires=REQUIRES,
    keywords='matrixos ampos pulse-eight',
    zip_safe=False)
