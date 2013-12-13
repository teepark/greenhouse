#!/usr/bin/env python
# vim: fileencoding=utf8:et:sw=4:ts=8:sts=4

import os
from setuptools import setup


VERSION = (2, 1, 8, "")

setup(
    name="greenhouse",
    description="An I/O parallelism library making use of coroutines",
    packages=[
        "greenhouse",
        "greenhouse.io",
        "greenhouse.emulation",
        "greenhouse.ext"],
    version=".".join(filter(None, map(str, VERSION))),
    author="Travis Parker",
    author_email="travis.parker@gmail.com",
    url="http://github.com/teepark/greenhouse",
    license="BSD",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Programming Language :: Python",
    ],
    install_requires=['greenlet'],
)
