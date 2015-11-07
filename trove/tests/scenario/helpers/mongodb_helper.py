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

from trove.tests.scenario.helpers.test_helper import TestHelper


class MongodbHelper(TestHelper):

    def __init__(self, expected_override_name):
        super(MongodbHelper, self).__init__(expected_override_name)

    def get_valid_database_definitions(self):
        return [{"name": 'db1'}, {"name": 'db2'}]

    def get_valid_user_definitions(self):
        return [{'name': 'db0.user1', 'password': 'password1',
                 'databases': []},
                {'name': 'db0.user2', 'password': 'password1',
                 'databases': [{'name': 'db1'}]},
                {'name': 'db1.user3', 'password': 'password1',
                 'databases': [{'name': 'db1'}, {'name': 'db2'}]}]

    def get_non_dynamic_group(self):
        return {'systemLog.verbosity': 4}

    def get_invalid_groups(self):
        return [{'net.maxIncomingConnections': -1},
                {'storage.mmapv1.nsSize': 4096},
                {'storage.journal.enabled': 'string_value'}]
