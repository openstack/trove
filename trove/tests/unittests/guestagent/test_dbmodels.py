#    Copyright 2012 OpenStack Foundation
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
import testtools
from trove.guestagent.db import models as dbmodels
from mock import MagicMock


class MySQLDatabaseTest(testtools.TestCase):

    def setUp(self):
        super(MySQLDatabaseTest, self).setUp()

        self.mysqlDb = dbmodels.ValidatedMySQLDatabase()
        self.origin_ignore_db = self.mysqlDb._ignore_dbs
        self.mysqlDb._ignore_dbs = ['mysql']

    def tearDown(self):
        super(MySQLDatabaseTest, self).tearDown()
        self.mysqlDb._ignore_dbs = self.origin_ignore_db

    def test_name(self):
        self.assertEqual(self.mysqlDb.name, None)

    def test_name_setter(self):
        test_name = "Anna"
        self.mysqlDb.name = test_name
        self.assertEqual(test_name, self.mysqlDb.name)

    def test_is_valid_positive(self):
        self.assertTrue(self.mysqlDb._is_valid('mysqldb'))

    def test_is_valid_negative(self):
        self.assertFalse(self.mysqlDb._is_valid('mysql'))


class MySQLUserTest(testtools.TestCase):
    def setUp(self):
        super(MySQLUserTest, self).setUp()
        self.mysqlUser = dbmodels.MySQLUser()

    def tearDown(self):
        super(MySQLUserTest, self).tearDown()

    def test_is_valid_negative(self):
        self.assertFalse(self.mysqlUser._is_valid(None))
        self.assertFalse(self.mysqlUser._is_valid("|;"))
        self.assertFalse(self.mysqlUser._is_valid("\\"))

    def test_is_valid_positive(self):
        self.assertTrue(self.mysqlUser._is_valid("real_name"))


class IsValidUsernameTest(testtools.TestCase):
    def setUp(self):
        super(IsValidUsernameTest, self).setUp()
        self.mysqlUser = dbmodels.MySQLUser()
        self.origin_is_valid = self.mysqlUser._is_valid
        self.origin_ignore_users = self.mysqlUser._ignore_users
        self.mysqlUser._ignore_users = ["king"]

    def tearDown(self):
        super(IsValidUsernameTest, self).tearDown()
        self.mysqlUser._is_valid = self.origin_is_valid
        self.mysqlUser._ignore_users = self.origin_ignore_users

    def test_is_valid_user_name(self):
        value = "trove"
        self.assertTrue(self.mysqlUser._is_valid_user_name(value))

    def test_is_valid_user_name_negative(self):
        self.mysqlUser._is_valid = MagicMock(return_value=False)
        self.assertFalse(self.mysqlUser._is_valid_user_name("trove"))

        self.mysqlUser._is_valid = MagicMock(return_value=True)
        self.assertFalse(self.mysqlUser._is_valid_user_name("king"))


class IsValidHostnameTest(testtools.TestCase):
    def setUp(self):
        super(IsValidHostnameTest, self).setUp()
        self.mysqlUser = dbmodels.MySQLUser()

    def tearDown(self):
        super(IsValidHostnameTest, self).tearDown()

    def test_is_valid_octet(self):
        self.assertTrue(self.mysqlUser._is_valid_host_name('192.168.1.1'))

    def test_is_valid_bad_octet(self):
        self.assertFalse(self.mysqlUser._is_valid_host_name('999.168.1.1'))

    def test_is_valid_global_wildcard(self):
        self.assertTrue(self.mysqlUser._is_valid_host_name('%'))

    def test_is_valid_prefix_wildcard(self):
        self.assertTrue(self.mysqlUser._is_valid_host_name('%.168.1.1'))

    def test_is_valid_suffix_wildcard(self):
        self.assertTrue(self.mysqlUser._is_valid_host_name('192.168.1.%'))
