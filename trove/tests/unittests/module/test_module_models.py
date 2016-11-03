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

import copy
from mock import Mock, patch

from trove.common import crypto_utils
from trove.common import exception
from trove.datastore import models as datastore_models
from trove.module import models
from trove.taskmanager import api as task_api
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class CreateModuleTest(trove_testtools.TestCase):

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    def setUp(self):
        util.init_db()
        self.context = Mock()
        self.name = "name"
        self.module_type = 'ping'
        self.contents = 'my_contents\n'

        super(CreateModuleTest, self).setUp()

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    def tearDown(self):
        super(CreateModuleTest, self).tearDown()

    def test_can_create_update_module(self):
        module = models.Module.create(
            self.context,
            self.name, self.module_type, self.contents,
            'my desc', 'my_tenant', None, None, False, True, False,
            False, 5, True)
        self.assertIsNotNone(module)
        new_module = copy.copy(module)
        models.Module.update(self.context, new_module, module, False)
        module.delete()

    def test_validate_action(self):
        # tenant_id, auto_apply, visible, priority_apply, full_access,
        # valid, exception, works_for_admin
        data = [
            ['tenant', False, True, False, None,
             True],

            ['tenant', True, True, False, None,
             False, exception.ModuleAccessForbidden],
            ['tenant', False, False, False, None,
             False, exception.ModuleAccessForbidden],
            ['tenant', False, True, True, None,
             False, exception.ModuleAccessForbidden],
            ['tenant', False, True, False, True,
             False, exception.ModuleAccessForbidden, False],
            ['tenant', False, True, False, False,
             False, exception.ModuleAccessForbidden],
            ['tenant', True, False, True, False,
             False, exception.ModuleAccessForbidden],

            ['tenant', True, False, True, True,
             False, exception.InvalidModelError, False],
        ]
        for datum in data:
            tenant = datum[0]
            auto_apply = datum[1]
            visible = datum[2]
            priority_apply = datum[3]
            full_access = datum[4]
            valid = datum[5]
            expected_exception = None
            if not valid:
                expected_exception = datum[6]
            context = Mock()
            context.is_admin = False
            works_for_admin = True
            if len(datum) > 7:
                works_for_admin = datum[7]
            if valid:
                models.Module.validate_action(
                    context, 'action', tenant, auto_apply, visible,
                    priority_apply, full_access)
            else:
                self.assertRaises(
                    expected_exception,
                    models.Module.validate_action, context, 'action', tenant,
                    auto_apply, visible, priority_apply, full_access)
                # also make sure that it works for admin
                if works_for_admin:
                    context.is_admin = True
                    models.Module.validate_action(
                        context, 'action', tenant, auto_apply, visible,
                        priority_apply, full_access)

    def _build_module(self, ds_id, ds_ver_id):
        module = Mock()
        module.datastore_id = ds_id
        module.datastore_version_id = ds_ver_id
        module.contents = crypto_utils.encode_data(
            crypto_utils.encrypt_data(
                'VGhpc2lzbXlkYXRhc3RyaW5n',
                'thisismylongkeytouse'))
        return module

    def test_validate(self):
        data = [
            [[self._build_module('ds', 'ds_ver')], 'ds', 'ds_ver', True],
            [[self._build_module('ds', None)], 'ds', 'ds_ver', True],
            [[self._build_module(None, None)], 'ds', 'ds_ver', True],

            [[self._build_module('ds', 'ds_ver')], 'ds', 'ds2_ver', False,
             exception.TroveError],
            [[self._build_module('ds', 'ds_ver')], 'ds2', 'ds_ver', False,
             exception.TroveError],
            [[self._build_module('ds', 'ds_ver')], 'ds2', 'ds2_ver', False,
             exception.TroveError],
            [[self._build_module('ds', None)], 'ds2', 'ds2_ver', False,
             exception.TroveError],
            [[self._build_module(None, None)], 'ds2', 'ds2_ver', True],

            [[self._build_module(None, 'ds_ver')], 'ds2', 'ds_ver', True],
        ]
        for datum in data:
            modules = datum[0]
            ds_id = datum[1]
            ds_ver_id = datum[2]
            match = datum[3]
            expected_exception = None
            if not match:
                expected_exception = datum[4]
            ds = Mock()
            ds.id = ds_id
            ds.name = ds_id
            ds_ver = Mock()
            ds_ver.id = ds_ver_id
            ds_ver.name = ds_ver_id
            ds_ver.datastore_id = ds_id
            with patch.object(datastore_models.Datastore, 'load',
                              return_value=ds):
                with patch.object(datastore_models.DatastoreVersion, 'load',
                                  return_value=ds_ver):
                    if match:
                        models.Modules.validate(modules, ds_id, ds_ver_id)
                    else:
                        self.assertRaises(
                            expected_exception,
                            models.Modules.validate,
                            modules, ds_id, ds_ver_id)
