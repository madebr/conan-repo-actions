# -*- coding: utf-8 -*-

import unittest

from conan_repo_actions.check_dependencies import CONAN_REF_REGEX_IN_SOURCE


class RefTests(unittest.TestCase):
    def test_regex_basic(self):
        match = CONAN_REF_REGEX_IN_SOURCE.match('"boost/1.70@myuser/mychannel"')
        self.assertIsNotNone(match)
        self.assertEqual(match['ref'], 'boost/1.70@myuser/mychannel')
        self.assertEqual(match['name'], 'boost')
        self.assertEqual(match['version'], '1.70')
        self.assertEqual(match['user'], 'myuser')
        self.assertEqual(match['channel'], 'mychannel')

    def test_regex_dot(self):
        match = CONAN_REF_REGEX_IN_SOURCE.match('"boost.asio/1.70@myuser/mychannel"')
        self.assertIsNotNone(match)
        self.assertEqual(match['ref'], 'boost.asio/1.70@myuser/mychannel')
        self.assertEqual(match['name'], 'boost.asio')
        self.assertEqual(match['version'], '1.70')
        self.assertEqual(match['user'], 'myuser')
        self.assertEqual(match['channel'], 'mychannel')

    def test_regex_underscore(self):
        match = CONAN_REF_REGEX_IN_SOURCE.match('"boost_asio/1.70@myuser/mychannel"')
        self.assertIsNotNone(match)
        self.assertEqual(match['ref'], 'boost_asio/1.70@myuser/mychannel')
        self.assertEqual(match['name'], 'boost_asio')
        self.assertEqual(match['version'], '1.70')
        self.assertEqual(match['user'], 'myuser')
        self.assertEqual(match['channel'], 'mychannel')

    def test_regex_hyphen(self):
        match = CONAN_REF_REGEX_IN_SOURCE.match('"boost-asio/1.70@myuser/mychannel"')
        self.assertIsNotNone(match)
        self.assertEqual(match['ref'], 'boost-asio/1.70@myuser/mychannel')
        self.assertEqual(match['name'], 'boost-asio')
        self.assertEqual(match['version'], '1.70')
        self.assertEqual(match['user'], 'myuser')
        self.assertEqual(match['channel'], 'mychannel')

    def test_regex_curly(self):
        match = CONAN_REF_REGEX_IN_SOURCE.match('"boost/{}@myuser/mychannel"')
        self.assertIsNotNone(match)
        self.assertEqual(match['ref'], 'boost/{}@myuser/mychannel')
        self.assertEqual(match['name'], 'boost')
        self.assertEqual(match['version'], '{}')
        self.assertEqual(match['user'], 'myuser')
        self.assertEqual(match['channel'], 'mychannel')
