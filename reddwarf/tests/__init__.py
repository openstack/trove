# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# See http://code.google.com/p/python-nose/issues/detail?id=373
# The code below enables nosetests to work with i18n _() blocks


import __builtin__
setattr(__builtin__, '_', lambda x: x)

import os
import unittest
import urlparse

import mox

from reddwarf.db import db_api
from reddwarf.common import config
from reddwarf.common import utils


def reddwarf_root_path():
    return os.path.join(os.path.dirname(__file__), "..", "..")


def reddwarf_bin_path(filename="."):
    return os.path.join(reddwarf_root_path(), "bin", filename)


def reddwarf_etc_path(filename="."):
    return os.path.join(reddwarf_root_path(), "etc", "reddwarf", filename)


def test_config_file():
    return reddwarf_etc_path("reddwarf.conf.sample")


class BaseTest(unittest.TestCase):

    def setUp(self):
        #maxDiff=None ensures diff output of assert methods are not truncated
        self.maxDiff = None

        self.mock = mox.Mox()
        conf, reddwarf_app = config.Config.load_paste_app(
            'reddwarfapp',
            {"config_file": test_config_file()},
            None)
        db_api.configure_db(conf)
        db_api.clean_db()
        super(BaseTest, self).setUp()

    def tearDown(self):
        self.mock.UnsetStubs()
        self.mock.VerifyAll()
        super(BaseTest, self).tearDown()

    def assertRaisesExcMessage(self, exception, message,
                               func, *args, **kwargs):
        """This is similar to assertRaisesRegexp in python 2.7"""

        try:
            func(*args, **kwargs)
            self.fail("Expected %r to raise %r" % (func, exception))
        except exception as error:
            self.assertIn(message, str(error))

    def assertIn(self, expected, actual):
        """This is similar to assertIn in python 2.7"""
        self.assertTrue(expected in actual,
                        "%r does not contain %r" % (actual, expected))

    def assertNotIn(self, expected, actual):
        self.assertFalse(expected in actual,
                         "%r does not contain %r" % (actual, expected))

    def assertIsNone(self, actual):
        """This is similar to assertIsNone in python 2.7"""
        self.assertEqual(actual, None)

    def assertIsNotNone(self, actual):
        """This is similar to assertIsNotNone in python 2.7"""
        self.assertNotEqual(actual, None)

    def assertItemsEqual(self, expected, actual):
        self.assertEqual(sorted(expected), sorted(actual))

    def assertModelsEqual(self, expected, actual):
        self.assertEqual(
            sorted(expected, key=lambda model: model.id),
            sorted(actual, key=lambda model: model.id))

    def assertUrlEqual(self, expected, actual):
        self.assertEqual(expected.partition("?")[0], actual.partition("?")[0])

        #params ordering might be different in the urls
        self.assertEqual(
            urlparse.parse_qs(expected.partition("?")[2]),
            urlparse.parse_qs(actual.partition("?")[2]))

    def assertErrorResponse(self, response, error_type, expected_error):
        self.assertEqual(response.status_int, error_type().code)
        self.assertIn(expected_error, response.body)

    def setup_uuid_with(self, fake_uuid):
        self.mock.StubOutWithMock(utils, "generate_uuid")
        utils.generate_uuid().MultipleTimes().AndReturn(fake_uuid)
