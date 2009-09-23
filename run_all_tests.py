#!/usr/bin/env python

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

sys.exit(bool(runner.run(suite)))
