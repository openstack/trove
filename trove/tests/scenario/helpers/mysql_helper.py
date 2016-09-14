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


class MysqlHelper(SqlHelper):

    def __init__(self, expected_override_name, report):
        super(MysqlHelper, self).__init__(expected_override_name, report,
                                          'mysql')

    def get_helper_credentials(self):
        return {'name': 'lite', 'password': 'litepass', 'database': 'firstdb'}

    def get_helper_credentials_root(self):
        return {'name': 'root', 'password': 'rootpass'}

    def get_valid_database_definitions(self):
        return [{'name': 'db1', 'character_set': 'latin2',
                 'collate': 'latin2_general_ci'},
                {'name': 'db2'}, {"name": 'db3'}]

    def get_valid_user_definitions(self):
        return [{'name': 'a_user1', 'password': 'password1', 'databases': [],
                 'host': '127.0.0.1'},
                {'name': 'a_user2', 'password': 'password1',
                 'databases': [{'name': 'db1'}], 'host': '0.0.0.0'},
                {'name': 'a_user3', 'password': 'password1',
                 'databases': [{'name': 'db1'}, {'name': 'db2'}]}]

    def get_dynamic_group(self):
        return {'key_buffer_size': 10485760,
                'join_buffer_size': 10485760}

    def get_non_dynamic_group(self):
        return {'innodb_buffer_pool_size': 10485760,
                'long_query_time': 59.1}

    def get_invalid_groups(self):
        return [{'key_buffer_size': -1}, {"join_buffer_size": 'string_value'}]

    def get_exposed_user_log_names(self):
        return ['general', 'slow_query']

    def get_unexposed_sys_log_names(self):
        return ['guest', 'error']
