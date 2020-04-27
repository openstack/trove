# Copyright 2016 Tesora, Inc.
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

from unittest import mock

from trove.common.db import models
from trove.tests.unittests import trove_testtools


class DatastoreSchemaTest(trove_testtools.TestCase):

    def setUp(self):
        super(DatastoreSchemaTest, self).setUp()
        self.dbname = 'testdb'
        self.serial_db = {'_name': self.dbname,
                          '_character_set': None,
                          '_collate': None}

    def tearDown(self):
        super(DatastoreSchemaTest, self).tearDown()

    def _empty_schema(self):
        return models.DatastoreSchema(deserializing=True)

    def test_init_name(self):
        database = models.DatastoreSchema(self.dbname)
        self.assertEqual(self.dbname, database.name)
        database2 = models.DatastoreSchema(name=self.dbname)
        self.assertEqual(self.dbname, database2.name)

    def test_init_no_name(self):
        self.assertRaises(RuntimeError, models.DatastoreSchema)

    @mock.patch.object(models.DatastoreSchema, 'verify_dict')
    def test_init_deserializing(self, mock_verify):
        database = models.DatastoreSchema.deserialize(self.serial_db)
        mock_verify.assert_any_call()
        self.assertEqual(self.dbname, database.name)

    def test_serialize(self):
        database = models.DatastoreSchema(self.dbname)
        self.assertEqual(self.serial_db, database.serialize())

    def test_name_property(self):
        test_name = "Anna"
        database = self._empty_schema()
        database.name = test_name
        self.assertEqual(test_name, database.name)

    def _do_validate_bad_schema_name(self, name):
        database = self._empty_schema()
        self.assertRaises(ValueError, database._validate_schema_name, name)

    def test_validate_name_empty(self):
        self._do_validate_bad_schema_name(None)

    @mock.patch.object(models.DatastoreSchema, '_max_schema_name_length',
                       new_callable=mock.PropertyMock)
    def test_validate_name_long(self, mock_max_len):
        mock_max_len.return_value = 5
        self._do_validate_bad_schema_name('toolong')

    @mock.patch.object(models.DatastoreSchema, '_is_valid_schema_name')
    def test_validate_name_invalid(self, mock_is_valid):
        mock_is_valid.return_value = False
        self._do_validate_bad_schema_name('notvalid')

    def test_verify_dict(self):
        database = models.DatastoreSchema(self.dbname)
        # using context patch because the property setter needs to work
        # properly during init for this test
        with mock.patch.object(
                models.DatastoreSchema, 'name',
                new_callable=mock.PropertyMock) as mock_name_property:
            database.verify_dict()
            mock_name_property.assert_called_with(self.dbname)

    def test_checks_pass(self):
        database = models.DatastoreSchema(self.dbname)
        database.check_reserved()
        database.check_create()
        database.check_delete()

    @mock.patch.object(models.DatastoreSchema, 'ignored_dbs',
                       new_callable=mock.PropertyMock)
    def test_checks_fail(self, mock_ignored_dbs):
        mock_ignored_dbs.return_value = [self.dbname]
        database = models.DatastoreSchema(self.dbname)
        self.assertRaises(ValueError, database.check_reserved)
        self.assertRaises(ValueError, database.check_create)
        self.assertRaises(ValueError, database.check_delete)


class DatastoreUserTest(trove_testtools.TestCase):

    def setUp(self):
        super(DatastoreUserTest, self).setUp()
        self.username = 'testuser'
        self.password = 'password'
        self.host = '192.168.0.1'
        self.dbname = 'testdb'
        self.serial_db = {'_name': self.dbname,
                          '_character_set': None,
                          '_collate': None}
        self.databases = [self.serial_db]
        self.host_wildcard = '%'
        self.serial_user_basic = {
            '_name': self.username, '_password': None,
            '_host': self.host_wildcard, '_databases': [],
            '_is_root': False
        }
        self.serial_user_full = {
            '_name': self.username, '_password': self.password,
            '_host': self.host, '_databases': self.databases,
            '_is_root': False
        }

    def tearDown(self):
        super(DatastoreUserTest, self).tearDown()

    def _empty_user(self):
        return models.DatastoreUser(deserializing=True)

    def _test_user_basic(self, user):
        self.assertEqual(self.username, user.name)
        self.assertIsNone(user.password)
        self.assertEqual(self.host_wildcard, user.host)
        self.assertEqual([], user.databases)

    def _test_user_full(self, user):
        self.assertEqual(self.username, user.name)
        self.assertEqual(self.password, user.password)
        self.assertEqual(self.host, user.host)
        self.assertEqual(self.databases, user.databases)

    def test_init_name(self):
        user1 = models.DatastoreUser(self.username)
        self._test_user_basic(user1)
        user2 = models.DatastoreUser(name=self.username)
        self._test_user_basic(user2)

    def test_init_no_name(self):
        self.assertRaises(ValueError, models.DatastoreUser)

    def test_init_options(self):
        user1 = models.DatastoreUser(self.username)
        self._test_user_basic(user1)
        user2 = models.DatastoreUser(self.username, self.password,
                                     self.host, self.dbname)
        self._test_user_full(user2)
        user3 = models.DatastoreUser(name=self.username,
                                     password=self.password,
                                     host=self.host,
                                     databases=self.dbname)
        self._test_user_full(user3)

    @mock.patch.object(models.DatastoreUser, 'verify_dict')
    def test_init_deserializing(self, mock_verify):
        user1 = models.DatastoreUser.deserialize(self.serial_user_basic)
        self._test_user_basic(user1)
        user2 = models.DatastoreUser.deserialize(self.serial_user_full)
        self._test_user_full(user2)
        self.assertEqual(2, mock_verify.call_count)

    def test_serialize(self):
        user1 = models.DatastoreUser(self.username)
        self.assertEqual(self.serial_user_basic, user1.serialize())
        user2 = models.DatastoreUser(self.username, self.password,
                                     self.host, self.dbname)
        self.assertEqual(self.serial_user_full, user2.serialize())

    @mock.patch.object(models.DatastoreUser, '_validate_user_name')
    def test_name_property(self, mock_validate):
        test_name = "Anna"
        user = self._empty_user()
        user.name = test_name
        self.assertEqual(test_name, user.name)
        mock_validate.assert_called_with(test_name)

    def _do_validate_bad_user_name(self, name):
        user = self._empty_user()
        self.assertRaises(ValueError, user._validate_user_name, name)

    def test_validate_name_empty(self):
        self._do_validate_bad_user_name(None)

    @mock.patch.object(models.DatastoreUser, '_max_user_name_length',
                       new_callable=mock.PropertyMock)
    def test_validate_name_long(self, mock_max_len):
        mock_max_len.return_value = 5
        self._do_validate_bad_user_name('toolong')

    @mock.patch.object(models.DatastoreUser, '_is_valid_user_name')
    def test_validate_name_invalid(self, mock_is_valid):
        mock_is_valid.return_value = False
        self._do_validate_bad_user_name('notvalid')

    @mock.patch.object(models.DatastoreUser, '_is_valid_password')
    def test_password_property(self, mock_validate):
        test_password = "NewPassword"
        user = self._empty_user()
        user.password = test_password
        mock_validate.assert_called_with(test_password)
        self.assertEqual(test_password, user.password)

    @mock.patch.object(models.DatastoreUser, '_is_valid_password')
    def test_password_property_error(self, mock_validate):
        mock_validate.return_value = False
        test_password = "NewPassword"
        user = self._empty_user()

        def test():
            user.password = test_password

        self.assertRaises(ValueError, test)

    @mock.patch.object(models.DatastoreUser, '_is_valid_host_name')
    def test_host_property(self, mock_validate):
        test_host = "192.168.0.2"
        user = self._empty_user()
        user.host = test_host
        mock_validate.assert_called_with(test_host)
        self.assertEqual(test_host, user.host)

    @mock.patch.object(models.DatastoreUser, '_is_valid_host_name')
    def test_host_property_error(self, mock_validate):
        mock_validate.return_value = False
        test_host = "192.168.0.2"
        user = self._empty_user()

        def test():
            user.host = test_host

        self.assertRaises(ValueError, test)

    @mock.patch.object(models.DatastoreUser, '_add_database')
    def test_databases_property(self, mock_add_database):
        test_dbname1 = 'otherdb'
        test_dbname2 = 'lastdb'
        user = self._empty_user()

        def test(value):
            user._databases.append({'_name': value,
                                    '_character_set': None,
                                    '_collate': None})

        mock_add_database.side_effect = test
        user.databases = self.dbname
        user.databases = [test_dbname1, test_dbname2]
        mock_add_database.assert_any_call(self.dbname)
        mock_add_database.assert_any_call(test_dbname1)
        mock_add_database.assert_any_call(test_dbname2)
        self.assertIn(self.serial_db, user.databases)
        self.assertIn({'_name': test_dbname1,
                       '_character_set': None,
                       '_collate': None}, user.databases)
        self.assertIn({'_name': test_dbname2,
                       '_character_set': None,
                       '_collate': None}, user.databases)

    def test_build_database_schema(self):
        user = self._empty_user()
        schema = user._build_database_schema(self.dbname)
        self.assertEqual(self.serial_db, schema.serialize())

    def test_add_database(self):
        user = self._empty_user()
        user._add_database(self.dbname)
        self.assertEqual([self.serial_db], user.databases)
        # check that adding an exsting db does nothing
        user._add_database(self.dbname)
        self.assertEqual([self.serial_db], user.databases)

    @mock.patch.object(models, 'DatastoreSchema')
    def test_deserialize_schema(self, mock_ds_schema):
        mock_ds_schema.deserialize = mock.Mock()
        user = self._empty_user()
        user.deserialize_schema(self.serial_db)
        mock_ds_schema.deserialize.assert_called_with(self.serial_db)

    @mock.patch.object(models.DatastoreUser, 'deserialize_schema')
    @mock.patch.object(models.DatastoreUser, 'host',
                       new_callable=mock.PropertyMock)
    @mock.patch.object(models.DatastoreUser, 'password',
                       new_callable=mock.PropertyMock)
    @mock.patch.object(models.DatastoreUser, 'name',
                       new_callable=mock.PropertyMock)
    def _test_verify_dict_with_mocks(self, user,
                                     mock_name_property,
                                     mock_password_property,
                                     mock_host_property,
                                     mock_deserialize_schema):
        user.verify_dict()
        mock_name_property.assert_called_with(self.username)
        mock_password_property.assert_called_with(self.password)
        mock_host_property.assert_called_with(self.host)
        mock_deserialize_schema.assert_called_with(self.serial_db)

    def test_verify_dict(self):
        user = models.DatastoreUser(self.username, self.password,
                                    self.host, self.dbname)
        self._test_verify_dict_with_mocks(user)

    def test_validate_dict_defaults(self):
        user = models.DatastoreUser(self.username)
        user.verify_dict()
        self.assertIsNone(user.password)
        self.assertEqual(self.host_wildcard, user.host)
        self.assertEqual([], user.databases)

    def test_is_root(self):
        user = models.DatastoreUser(self.username)
        self.assertFalse(user._is_root)
        user.make_root()
        self.assertTrue(user._is_root)

    def test_checks_pass(self):
        user = models.DatastoreUser(self.username)
        user.check_reserved()
        user.check_create()
        user.check_delete()

    @mock.patch.object(models.DatastoreUser, 'ignored_users',
                       new_callable=mock.PropertyMock)
    def test_checks_fail(self, mock_ignored_users):
        mock_ignored_users.return_value = [self.username]
        user = models.DatastoreUser(self.username)
        self.assertRaises(ValueError, user.check_reserved)
        self.assertRaises(ValueError, user.check_create)
        self.assertRaises(ValueError, user.check_delete)
