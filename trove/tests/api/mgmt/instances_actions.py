#    Copyright 2013 OpenStack Foundation
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

from novaclient.v2.servers import Server
from proboscis import after_class
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis import before_class
from proboscis import SkipTest
from proboscis import test
from unittest import mock

from trove.backup import models as backup_models
from trove.backup import state
from trove.common.context import TroveContext
from trove.common import exception
import trove.common.instance as tr_instance
from trove.extensions.mgmt.instances.models import MgmtInstance
from trove.extensions.mgmt.instances.service import MgmtInstanceController
from trove.instance import models as imodels
from trove.instance.models import DBInstance
from trove.instance.tasks import InstanceTasks
from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.action.reset-task-status"


class MgmtInstanceBase(object):

    def setUp(self):
        self._create_instance()
        self.controller = MgmtInstanceController()

    def tearDown(self):
        self.db_info.delete()

    def _create_instance(self):
        self.context = TroveContext(is_admin=True)
        self.tenant_id = 999
        self.db_info = DBInstance.create(
            id="inst-id-1",
            name="instance",
            flavor_id=1,
            datastore_version_id=test_config.dbaas_datastore_version_id,
            tenant_id=self.tenant_id,
            volume_size=None,
            task_status=InstanceTasks.NONE)
        self.server = mock.MagicMock(spec=Server)
        self.instance = imodels.Instance(
            self.context,
            self.db_info,
            self.server,
            datastore_status=imodels.InstanceServiceStatus(
                tr_instance.ServiceStatuses.RUNNING))

    def _make_request(self, path='/', context=None, **kwargs):
        from webob import Request
        path = '/'
        print("path: %s" % path)
        return Request.blank(path=path, environ={'trove.context': context},
                             **kwargs)

    def _reload_db_info(self):
        self.db_info = DBInstance.find_by(id=self.db_info.id, deleted=False)


@test(groups=[GROUP])
class RestartTaskStatusTests(MgmtInstanceBase):

    @before_class
    def setUp(self):
        super(RestartTaskStatusTests, self).setUp()
        self.backups_to_clear = []

    @after_class
    def tearDown(self):
        super(RestartTaskStatusTests, self).tearDown()

    def _change_task_status_to(self, new_task_status):
        self.db_info.task_status = new_task_status
        self.db_info.save()

    def _make_request(self, path='/', context=None, **kwargs):
        req = super(RestartTaskStatusTests, self)._make_request(path, context,
                                                                **kwargs)
        req.method = 'POST'
        body = {'reset-task-status': {}}
        return req, body

    def reset_task_status(self):
        with mock.patch.object(MgmtInstance, 'load') as mock_load:
            mock_load.return_value = self.instance
            req, body = self._make_request(context=self.context)
            self.controller = MgmtInstanceController()
            resp = self.controller.action(req, body, self.tenant_id,
                                          self.db_info.id)

            mock_load.assert_called_once_with(context=self.context,
                                              id=self.db_info.id)
        return resp

    @test
    def mgmt_restart_task_requires_admin_account(self):
        context = TroveContext(is_admin=False)
        req, body = self._make_request(context=context)
        self.controller = MgmtInstanceController()
        assert_raises(exception.Forbidden, self.controller.action,
                      req, body, self.tenant_id, self.db_info.id)

    @test
    def mgmt_restart_task_returns_json(self):
        resp = self.reset_task_status()
        out = resp.data("application/json")
        assert_equal(out, None)

    @test
    def mgmt_restart_task_changes_status_to_none(self):
        self._change_task_status_to(InstanceTasks.BUILDING)
        self.reset_task_status()
        self._reload_db_info()
        assert_equal(self.db_info.task_status, InstanceTasks.NONE)

    @test
    def mgmt_reset_task_status_clears_backups(self):
        if CONFIG.fake_mode:
            raise SkipTest("Test requires an instance.")

        self.reset_task_status()
        self._reload_db_info()
        assert_equal(self.db_info.task_status, InstanceTasks.NONE)

        user = test_config.users.find_user(Requirements(is_admin=False))
        dbaas = create_dbaas_client(user)
        admin = test_config.users.find_user(Requirements(is_admin=True))
        admin_dbaas = create_dbaas_client(admin)
        result = dbaas.instances.backups(self.db_info.id)
        assert_equal(0, len(result))

        # Create some backups.
        backup_models.DBBackup.create(
            name="forever_new",
            description="forever new",
            tenant_id=self.tenant_id,
            state=state.BackupState.NEW,
            instance_id=self.db_info.id,
            deleted=False)

        backup_models.DBBackup.create(
            name="forever_build",
            description="forever build",
            tenant_id=self.tenant_id,
            state=state.BackupState.BUILDING,
            instance_id=self.db_info.id,
            deleted=False)

        backup_models.DBBackup.create(
            name="forever_completed",
            description="forever completed",
            tenant_id=self.tenant_id,
            state=state.BackupState.COMPLETED,
            instance_id=self.db_info.id,
            deleted=False)

        # List the backups for this instance.
        # There ought to be three in the admin tenant, but
        # none in a different user's tenant.
        result = dbaas.instances.backups(self.db_info.id)
        assert_equal(0, len(result))
        result = admin_dbaas.instances.backups(self.db_info.id)
        assert_equal(3, len(result))
        self.backups_to_clear = result

        # Reset the task status.
        self.reset_task_status()
        self._reload_db_info()
        result = admin_dbaas.instances.backups(self.db_info.id)
        assert_equal(3, len(result))
        for backup in result:
            if backup.name == 'forever_completed':
                assert_equal(backup.status,
                             state.BackupState.COMPLETED)
            else:
                assert_equal(backup.status, state.BackupState.FAILED)

    @test(runs_after=[mgmt_reset_task_status_clears_backups])
    def clear_test_backups(self):
        for backup in self.backups_to_clear:
            found_backup = backup_models.DBBackup.find_by(id=backup.id)
            found_backup.delete()
        admin = test_config.users.find_user(Requirements(is_admin=True))
        admin_dbaas = create_dbaas_client(admin)
        if not CONFIG.fake_mode:
            result = admin_dbaas.instances.backups(self.db_info.id)
            assert_equal(0, len(result))
