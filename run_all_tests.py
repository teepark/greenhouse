#!/usr/bin/env python

import doctest
import glob
import optparse
import os
import sys
import unittest

import greenhouse

def main():
    parser = optparse.OptionParser()
    parser.add_option("-v",
            action="count",
            dest="plusv",
            help="Be more verbose.")
    parser.add_option("-q",
            action="count",
            dest="minusv",
            help="Be less verbose.")
    parser.add_option("--verbosity",
            default=1,
            type=int,
            help="Set verbosity; --verbose=2 is the same as -v")

    options, args = parser.parse_args()

    options.verbosity += options.plusv or 0
    options.verbosity -= options.minusv or 0

    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    runner = unittest.TextTestRunner(verbosity=options.verbosity)

    for fname in glob.glob(os.path.join("tests", "*.py")):
        suite.addTest(loader.loadTestsFromName(
            fname.replace("/", ".")[:-3]))

    dtfinder = doctest.DocTestFinder()
    for fname in glob.glob(os.path.join("greenhouse", "*.py")):
        mod = __import__(fname.replace("/", ".")[:-3])
        if dtfinder.find(mod):
            suite.addTest(doctest.DocTestSuite(mod))

    sys.exit(runner.run(suite).wasSuccessful())

if __name__ == '__main__':
    main()
