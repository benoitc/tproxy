#!/usr/bin/env python
# -*- coding: utf-8 -
#
# This file is part of tproxy released under the MIT license.
# See the NOTICE for more information.

from __future__ import with_statement

from glob import glob
from imp import load_source
import os
import sys


CLASSIFIERS = [
        'Development Status :: 4 - Beta',
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: Internet',
        'Topic :: Internet',
        'Topic :: Internet :: Proxy Servers',
        'Topic :: Utilities',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Networking'
    ]

MODULES = (
        'tproxy',
    )

SCRIPTS = glob("bin/tproxy*")

def main():
    if "--setuptools" in sys.argv:
        sys.argv.remove("--setuptools")
        from setuptools import setup
        use_setuptools = True
    else:
        from distutils.core import setup
        use_setuptools = False

    tproxy = load_source("tproxy", os.path.join("tproxy",
        "__init__.py"))

    # read long description
    with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
        long_description = f.read()


    PACKAGES = {}
    for name in MODULES:
        PACKAGES[name] = name.replace(".", "/")

    DATA_FILES = [
        ('tproxy', ["LICENSE", "MANIFEST.in", "NOTICE", "README.rst",
                        "THANKS",])
        ]

    options = dict(
            name = 'tproxy',
            version = tproxy.__version__,
            description = 'WSGI HTTP Server for UNIX',
            long_description = long_description,
            author = 'Benoit Chesneau',
            author_email = 'benoitc@e-engura.com',
            license = 'MIT',
            url = 'http://github.com/benoitc/tproxy',
            classifiers = CLASSIFIERS,
            packages = PACKAGES.keys(),
            package_dir = PACKAGES,
            scripts = SCRIPTS,
            data_files = DATA_FILES,
    )

        
    setup(**options)

if __name__ == "__main__":
    main()

