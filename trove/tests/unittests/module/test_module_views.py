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
#

from mock import Mock, patch
from trove.datastore import models
from trove.module.views import DetailedModuleView
from trove.tests.unittests import trove_testtools


class ModuleViewsTest(trove_testtools.TestCase):

    def setUp(self):
        super(ModuleViewsTest, self).setUp()

    def tearDown(self):
        super(ModuleViewsTest, self).tearDown()


class DetailedModuleViewTest(trove_testtools.TestCase):

    def setUp(self):
        super(DetailedModuleViewTest, self).setUp()
        self.module = Mock()
        self.module.name = 'test_module'
        self.module.type = 'test'
        self.module.md5 = 'md5-hash'
        self.module.created = 'Yesterday'
        self.module.updated = 'Now'
        self.module.datastore = 'mysql'
        self.module.datastore_version = '5.7'
        self.module.auto_apply = False
        self.module.tenant_id = 'my_tenant'
        self.module.is_admin = False
        self.module.priority_apply = False
        self.module.apply_order = 5

    def tearDown(self):
        super(DetailedModuleViewTest, self).tearDown()

    def test_data(self):
        datastore = Mock()
        datastore.name = self.module.datastore
        ds_version = Mock()
        ds_version.name = self.module.datastore_version
        with patch.object(models, 'get_datastore_version',
                          Mock(return_value=(datastore, ds_version))):
            view = DetailedModuleView(self.module)
            result = view.data()
            self.assertEqual(self.module.name, result['module']['name'])
            self.assertEqual(self.module.type, result['module']['type'])
            self.assertEqual(self.module.md5, result['module']['md5'])
            self.assertEqual(self.module.created, result['module']['created'])
            self.assertEqual(self.module.updated, result['module']['updated'])
            self.assertEqual(self.module.datastore_version,
                             result['module']['datastore_version'])
            self.assertEqual(self.module.datastore,
                             result['module']['datastore'])
            self.assertEqual(self.module.auto_apply,
                             result['module']['auto_apply'])
            self.assertEqual(self.module.tenant_id,
                             result['module']['tenant_id'])
            self.assertEqual(self.module.is_admin,
                             result['module']['is_admin'])
            self.assertEqual(self.module.priority_apply,
                             result['module']['priority_apply'])
            self.assertEqual(self.module.apply_order,
                             result['module']['apply_order'])
