#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from setuptools import setup
from setuptools import find_packages

INSTALL_REQUIRES = [
    'argcomplete',
]

DATA_FILES = [
    ('/etc/network/ifupdown2/', ['etc/network/ifupdown2/addons.conf']),
    ('/etc/network/ifupdown2/', ['etc/network/ifupdown2/ifupdown2.conf']),
]

SCRIPTS = []

ENTRY_POINTS = {}


def build_deb_package():
    try:
        return sys.argv[sys.argv.index('--root') + 1].endswith('/debian/ifupdown2')
    except Exception:
        pass
    return False


if not build_deb_package():
    ENTRY_POINTS = {
        'console_scripts': [
            'ifup = ifupdown2.__main__:main',
            'ifdown = ifupdown2.__main__:main',
            'ifquery = ifupdown2.__main__:main',
            'ifreload = ifupdown2.__main__:main',
        ],
    }

setup(
    author='Julien Fortin',
    author_email='julien@cumulusnetworks.com',
    maintainer='Julien Fortin',
    maintainer_email='julien@cumulusnetworks.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Topic :: System :: Networking',
        'Topic :: System :: Systems Administration'
    ],
    description='interface network manager',
    install_requires=INSTALL_REQUIRES,
    license='GNU General Public License v2',
    keywords='ifupdown2',
    name='ifupdown2',
    packages=find_packages(),
    url='https://github.com/CumulusNetworks/ifupdown2',
    version='3.0.0',
    data_files=DATA_FILES,
    setup_requires=['setuptools'],
    scripts=SCRIPTS,
    entry_points=ENTRY_POINTS
)
