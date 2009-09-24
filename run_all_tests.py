#!/usr/bin/env python

import doctest
import glob
import os
import sys
import unittest

import greenhouse


suite = unittest.TestSuite()
loader = unittest.TestLoader()
runner = unittest.TextTestRunner()

for fname in glob.glob(os.path.join("tests", "*.py")):
    suite.addTest(loader.loadTestsFromName(fname.replace("/", ".")[:-3]))

dtfinder = doctest.DocTestFinder()
for fname in glob.glob(os.path.join("greenhouse", "*.py")):
    mod = __import__(fname.replace("/", ".")[:-3])
    if dtfinder.find(mod):
        suite.addTest(doctest.DocTestSuite(mod))

sys.exit(bool(runner.run(suite)))
