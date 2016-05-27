# Copyright 2016 Tesora Inc.
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

from proboscis import SkipTest

from trove.tests.scenario.helpers.sql_helper import SqlHelper


class VerticaHelper(SqlHelper):

    def __init__(self, expected_override_name, report):
        super(VerticaHelper, self).__init__(expected_override_name, report,
                                            'vertica')

    def get_helper_credentials(self):
        return {'name': 'lite', 'password': 'litepass', 'database': 'lite'}

    def get_valid_user_definitions(self):
        return [{'name': 'user1', 'password': 'password1', 'databases': []},
                {'name': 'user2', 'password': 'password1',
                 'databases': [{'name': 'db1'}]},
                {'name': 'user3', 'password': 'password1',
                 'databases': [{'name': 'db1'}, {'name': 'db2'}]}]

    def add_actual_data(self, *args, **kwargs):
        raise SkipTest("Adding data to Vertica is not implemented")

    def verify_actual_data(self, *args, **kwargs):
        raise SkipTest("Verifying data in Vertica is not implemented")

    def remove_actual_data(self, *args, **kwargs):
        raise SkipTest("Removing data from Vertica is not implemented")

    def get_dynamic_group(self):
        return {'ActivePartitionCount': 3}

    def get_non_dynamic_group(self):
        return {'BlockCacheSize': 1024}

    def get_invalid_groups(self):
        return [{'timezone': 997},
                {"max_worker_processes": 'string_value'},
                {"standard_conforming_strings": 'string_value'}]
