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

from trove.tests.scenario.helpers.sql_helper import SqlHelper


class PostgresqlHelper(SqlHelper):

    def __init__(self, expected_override_name, report):
        super(PostgresqlHelper, self).__init__(expected_override_name, report,
                                               'postgresql')

    @property
    def test_schema(self):
        return 'public'

    def get_helper_credentials(self):
        # There must be a database with the same name as the user in order
        # for the user to be able to login.
        return {'name': 'lite', 'password': 'litepass', 'database': 'lite'}

    def get_helper_credentials_root(self):
        return {'name': 'postgres', 'password': 'rootpass'}

    def get_valid_database_definitions(self):
        return [{'name': 'db1'}, {'name': 'db2'}, {'name': 'db3'}]

    def get_valid_user_definitions(self):
        return [{'name': 'user1', 'password': 'password1', 'databases': []},
                {'name': 'user2', 'password': 'password1',
                 'databases': [{'name': 'db1'}]},
                {'name': 'user3', 'password': 'password1',
                 'databases': [{'name': 'db1'}, {'name': 'db2'}]}]

    def get_dynamic_group(self):
        return {'effective_cache_size': '528MB',
                'log_min_duration_statement': 257}

    def get_non_dynamic_group(self):
        return {'max_connections': 113}

    def get_invalid_groups(self):
        return [{'timezone': 997},
                {"vacuum_cost_delay": 'string_value'},
                {"standard_conforming_strings": 'string_value'}]

    def get_configuration_value(self, property_name, host, *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        cmd = "SHOW %s;" % property_name
        row = client.execute(cmd).fetchone()
        return row[0]

    def get_exposed_user_log_names(self):
        return ['general']

    def log_enable_requires_restart(self):
        return True
