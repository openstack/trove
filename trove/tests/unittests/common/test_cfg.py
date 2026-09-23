# Copyright 2026 PS Cloud Services.
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

from trove.common import cfg
from trove.tests.unittests import trove_testtools


class ConfigurationPropertyTest(trove_testtools.TestCase):

    @mock.patch.object(cfg.LOG, 'warning')
    @mock.patch.object(cfg, 'CONF')
    def test_get_ignored_users_uses_datastore_manager(
            self, mock_conf, mock_warning):
        mock_conf.datastore_manager = 'mysql'
        datastore_config = mock_conf.get.return_value
        datastore_config.get.return_value = ['os_admin', 'postgres']

        ignored_users = cfg.get_ignored_users(datastore_manager='postgresql')

        self.assertEqual(['os_admin', 'postgres'], ignored_users)
        mock_conf.get.assert_called_once_with('postgresql')
        datastore_config.get.assert_called_once_with('ignore_users')
        mock_warning.assert_not_called()

    @mock.patch.object(cfg.LOG, 'warning')
    @mock.patch.object(cfg, 'CONF')
    def test_get_ignored_dbs_uses_datastore_manager(
            self, mock_conf, mock_warning):
        mock_conf.datastore_manager = 'mysql'
        datastore_config = mock_conf.get.return_value
        datastore_config.get.return_value = ['os_admin', 'postgres']

        ignored_dbs = cfg.get_ignored_dbs(datastore_manager='postgresql')

        self.assertEqual(['os_admin', 'postgres'], ignored_dbs)
        mock_conf.get.assert_called_once_with('postgresql')
        datastore_config.get.assert_called_once_with('ignore_dbs')
        mock_warning.assert_not_called()
