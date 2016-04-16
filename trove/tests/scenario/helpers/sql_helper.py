# Copyright 2015 Tesora Inc.
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

import sqlalchemy
from sqlalchemy import MetaData, Table, Column, Integer

from trove.tests.scenario.helpers.test_helper import TestHelper
from trove.tests.scenario.runners.test_runners import TestRunner


class SqlHelper(TestHelper):

    """This mixin provides data handling helper functions for SQL datastores.
    """

    DATA_COLUMN_NAME = 'value'

    def __init__(self, expected_override_name, protocol, port=None):
        super(SqlHelper, self).__init__(expected_override_name)

        self.protocol = protocol
        self.port = port
        self.credentials = self.get_helper_credentials()
        self.credentials_root = self.get_helper_credentials_root()

        self._schema_metadata = MetaData()
        self._data_cache = dict()

    @property
    def test_schema(self):
        return self.credentials['database']

    def create_client(self, host, *args, **kwargs):
        username = kwargs.get("username")
        password = kwargs.get("password")
        if username and password:
            creds = {"name": username, "password": password}
            return sqlalchemy.create_engine(
                self._build_connection_string(host, creds))
        return sqlalchemy.create_engine(
            self._build_connection_string(host, self.credentials))

    def _build_connection_string(self, host, creds):
        if self.port:
            host = "%s:%d" % (host, self.port)

        credentials = {'protocol': self.protocol,
                       'host': host,
                       'user': creds.get('name', ''),
                       'password': creds.get('password', ''),
                       'database': creds.get('database', '')}
        return ('%(protocol)s://%(user)s:%(password)s@%(host)s/%(database)s'
                % credentials)

    # Add data overrides
    def add_actual_data(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        self._create_data_table(client, self.test_schema, data_label)
        count = self._count_data_rows(client, self.test_schema, data_label)
        if count == 0:
            self._insert_data_rows(client, self.test_schema, data_label,
                                   data_size)

    def _create_data_table(self, client, schema_name, table_name):
        Table(
            table_name, self._schema_metadata,
            Column(self.DATA_COLUMN_NAME, Integer(),
                   nullable=False, default=0),
            keep_existing=True, schema=schema_name
        ).create(client, checkfirst=True)

    def _count_data_rows(self, client, schema_name, table_name):
        data_table = self._get_schema_table(schema_name, table_name)
        return client.execute(data_table.count()).scalar()

    def _insert_data_rows(self, client, schema_name, table_name, data_size):
        data_table = self._get_schema_table(schema_name, table_name)
        client.execute(data_table.insert(), self._get_dataset(data_size))

    def _get_schema_table(self, schema_name, table_name):
        qualified_table_name = '%s.%s' % (schema_name, table_name)
        return self._schema_metadata.tables.get(qualified_table_name)

    def _get_dataset(self, data_size):
        cache_key = str(data_size)
        if cache_key in self._data_cache:
            return self._data_cache.get(cache_key)

        data = self._generate_dataset(data_size)
        self._data_cache[cache_key] = data
        return data

    def _generate_dataset(self, data_size):
        return [{self.DATA_COLUMN_NAME: value}
                for value in range(1, data_size + 1)]

    # Remove data overrides
    def remove_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host)
        self._drop_table(client, self.test_schema, data_label)

    def _drop_table(self, client, schema_name, table_name):
        data_table = self._get_schema_table(schema_name, table_name)
        data_table.drop(client, checkfirst=True)

    # Verify data overrides
    def verify_actual_data(self, data_label, data_Start, data_size, host,
                           *args, **kwargs):
        expected_data = [(item[self.DATA_COLUMN_NAME],)
                         for item in self._get_dataset(data_size)]
        client = self.get_client(host, *args, **kwargs)
        actual_data = self._select_data_rows(client, self.test_schema,
                                             data_label)

        TestRunner.assert_equal(len(expected_data), len(actual_data),
                                "Unexpected number of result rows.")
        TestRunner.assert_list_elements_equal(
            expected_data, actual_data, "Unexpected rows in the result set.")

    def _select_data_rows(self, client, schema_name, table_name):
        data_table = self._get_schema_table(schema_name, table_name)
        return client.execute(data_table.select()).fetchall()

    def ping(self, host, *args, **kwargs):
        root_client = self.get_client(host, *args, **kwargs)
        root_client.execute("SELECT 1;")
