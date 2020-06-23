# Copyright (c) 2018 NEC, Corp.
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

from unittest.mock import Mock
from unittest.mock import patch
from oslo_upgradecheck.upgradecheck import Code

from trove.cmd import status
from trove.tests.unittests import trove_testtools


@patch("trove.cmd.status.db.get_db_api")
@patch("trove.cmd.status.DBInstance")
class TestUpgradeChecksInstancesWithTasks(trove_testtools.TestCase):
    def setUp(self):
        super(TestUpgradeChecksInstancesWithTasks, self).setUp()
        self.cmd = status.Checks()
        self.fake_db_api = Mock()

    def test__check_no_instances_with_tasks(self, mock_instance,
                                            fake_get_db_api):
        fake_get_db_api.return_value = self.fake_db_api

        mock_instance.query.return_value.filter.return_value.filter_by.\
            return_value.count.return_value = 0

        check_result = self.cmd._check_instances_with_running_tasks()
        self.assertEqual(Code.SUCCESS, check_result.code)

    def test__check_instances_with_tasks(self, mock_instance,
                                         fake_get_db_api):
        fake_get_db_api.return_value = self.fake_db_api

        mock_instance.query.return_value.filter.return_value.filter_by.\
            return_value.count.return_value = 1

        check_result = self.cmd._check_instances_with_running_tasks()
        self.assertEqual(Code.WARNING, check_result.code)
