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

from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster

from trove.tests.scenario.helpers.test_helper import TestHelper
from trove.tests.scenario.runners.test_runners import TestRunner


class CassandraClient(object):

    # Cassandra 2.1 only supports protocol versions 3 and lower.
    NATIVE_PROTOCOL_VERSION = 3

    def __init__(self, contact_points, user, password, keyspace):
        super(CassandraClient, self).__init__()
        self._cluster = None
        self._session = None
        self._cluster = Cluster(
            contact_points=contact_points,
            auth_provider=PlainTextAuthProvider(user, password),
            protocol_version=self.NATIVE_PROTOCOL_VERSION)
        self._session = self._connect(keyspace)

    def _connect(self, keyspace):
        if not self._cluster.is_shutdown:
            return self._cluster.connect(keyspace)
        else:
            raise Exception("Cannot perform this operation on a terminated "
                            "cluster.")

    @property
    def session(self):
        return self._session

    def __del__(self):
        if self._cluster is not None:
            self._cluster.shutdown()

        if self._session is not None:
            self._session.shutdown()


class CassandraHelper(TestHelper):

    DATA_COLUMN_NAME = 'value'

    def __init__(self, expected_override_name, report):
        super(CassandraHelper, self).__init__(expected_override_name, report)

        self._data_cache = dict()

    def create_client(self, host, *args, **kwargs):
        user = self.get_helper_credentials()
        username = kwargs.get('username', user['name'])
        password = kwargs.get('password', user['password'])
        database = kwargs.get('database', user['database'])
        return CassandraClient([host], username, password, database)

    def add_actual_data(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        self._create_data_table(client, data_label)
        stmt = client.session.prepare("INSERT INTO %s (%s) VALUES (?)"
                                      % (data_label, self.DATA_COLUMN_NAME))
        count = self._count_data_rows(client, data_label)
        if count == 0:
            for value in self._get_dataset(data_size):
                client.session.execute(stmt, [value])

    def _create_data_table(self, client, table_name):
        client.session.execute('CREATE TABLE IF NOT EXISTS %s '
                               '(%s INT PRIMARY KEY)'
                               % (table_name, self.DATA_COLUMN_NAME))

    def _count_data_rows(self, client, table_name):
        rows = client.session.execute('SELECT COUNT(*) FROM %s' % table_name)
        if rows:
            return rows[0][0]
        return 0

    def _get_dataset(self, data_size):
        cache_key = str(data_size)
        if cache_key in self._data_cache:
            return self._data_cache.get(cache_key)

        data = self._generate_dataset(data_size)
        self._data_cache[cache_key] = data
        return data

    def _generate_dataset(self, data_size):
        return range(1, data_size + 1)

    def remove_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        self._drop_table(client, data_label)

    def _drop_table(self, client, table_name):
        client.session.execute('DROP TABLE %s' % table_name)

    def verify_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        expected_data = self._get_dataset(data_size)
        client = self.get_client(host, *args, **kwargs)
        actual_data = self._select_data_rows(client, data_label)

        TestRunner.assert_equal(len(expected_data), len(actual_data),
                                "Unexpected number of result rows.")
        for expected_row in expected_data:
            TestRunner.assert_true(expected_row in actual_data,
                                   "Row not found in the result set: %s"
                                   % expected_row)

    def _select_data_rows(self, client, table_name):
        rows = client.session.execute('SELECT %s FROM %s'
                                      % (self.DATA_COLUMN_NAME, table_name))
        return [value[0] for value in rows]

    def get_helper_credentials(self):
        return {'name': 'lite', 'password': 'litepass', 'database': 'firstdb'}

    def ping(self, host, *args, **kwargs):
        try:
            self.get_client(host, *args, **kwargs)
            return True
        except Exception:
            return False

    def get_valid_database_definitions(self):
        return [{"name": 'db1'}, {"name": 'db2'}, {"name": 'db3'}]

    def get_valid_user_definitions(self):
        return [{'name': 'user1', 'password': 'password1',
                 'databases': []},
                {'name': 'user2', 'password': 'password1',
                 'databases': [{'name': 'db1'}]},
                {'name': 'user3', 'password': 'password1',
                 'databases': [{'name': 'db1'}, {'name': 'db2'}]}]

    def get_non_dynamic_group(self):
        return {'sstable_preemptive_open_interval_in_mb': 40}

    def get_invalid_groups(self):
        return [{'sstable_preemptive_open_interval_in_mb': -1},
                {'sstable_preemptive_open_interval_in_mb': 'string_value'}]
