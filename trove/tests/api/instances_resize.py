# Copyright 2013 OpenStack Foundation
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

from mock import Mock
from mox3 import mox
from testtools import TestCase
from proboscis import test

from novaclient.exceptions import BadRequest
from novaclient.v1_1.servers import Server

from trove.common.exception import PollTimeOut
from trove.common import template
from trove.common import utils
from trove.common.context import TroveContext
from trove.common import instance as rd_instance
from trove.datastore.models import DatastoreVersion
from trove.guestagent import api as guest
from trove.instance.models import DBInstance
from trove.instance.models import InstanceServiceStatus
from trove.instance.tasks import InstanceTasks
from trove.openstack.common.rpc.common import RPCException
from trove.taskmanager import models as models
from trove.tests.fakes import nova
from trove.tests.util import test_config

GROUP = 'dbaas.api.instances.resize'

OLD_FLAVOR_ID = 1
NEW_FLAVOR_ID = 2
OLD_FLAVOR = nova.FLAVORS.get(OLD_FLAVOR_ID)
NEW_FLAVOR = nova.FLAVORS.get(NEW_FLAVOR_ID)


class ResizeTestBase(TestCase):

    def _init(self):
        self.mock = mox.Mox()
        self.instance_id = 500
        context = TroveContext()
        self.db_info = DBInstance.create(
            name="instance",
            flavor_id=OLD_FLAVOR_ID,
            tenant_id=999,
            volume_size=None,
            datastore_version_id=test_config.dbaas_datastore_version_id,
            task_status=InstanceTasks.RESIZING)
        self.server = self.mock.CreateMock(Server)
        self.instance = models.BuiltInstanceTasks(
            context,
            self.db_info,
            self.server,
            datastore_status=InstanceServiceStatus.create(
                instance_id=self.db_info.id,
                status=rd_instance.ServiceStatuses.RUNNING))
        self.instance.server.flavor = {'id': OLD_FLAVOR_ID}
        self.guest = self.mock.CreateMock(guest.API)
        self.instance._guest = self.guest
        self.instance.refresh_compute_server_info = lambda: None
        self.instance._refresh_datastore_status = lambda: None
        self.mock.StubOutWithMock(self.instance, 'update_db')
        self.mock.StubOutWithMock(self.instance,
                                  'set_datastore_status_to_paused')
        self.poll_until_mocked = False
        self.action = None

    def tearDown(self):
        super(ResizeTestBase, self).tearDown()
        self.mock.UnsetStubs()
        self.db_info.delete()

    def _execute_action(self):
        self.instance.update_db(task_status=InstanceTasks.NONE)
        self.mock.ReplayAll()
        excs = (Exception)
        self.assertRaises(excs, self.action.execute)
        self.mock.VerifyAll()

    def _stop_db(self, reboot=True):
        self.guest.stop_db(do_not_start_on_reboot=reboot)
        self.instance.datastore_status.status = (
            rd_instance.ServiceStatuses.SHUTDOWN)

    def _server_changes_to(self, new_status, new_flavor_id):
        def change():
            self.server.status = new_status
            self.instance.server.flavor['id'] = new_flavor_id

        if not self.poll_until_mocked:
            self.mock.StubOutWithMock(utils, "poll_until")
            self.poll_until_mocked = True
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)\
            .WithSideEffects(lambda ignore, sleep_time, time_out: change())

    def _nova_resizes_successfully(self):
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("VERIFY_RESIZE", NEW_FLAVOR_ID)


@test(groups=[GROUP, GROUP + '.resize'])
class ResizeTests(ResizeTestBase):

    def setUp(self):
        super(ResizeTests, self).setUp()
        self._init()
        # By the time flavor objects pass over amqp to the
        # resize action they have been turned into dicts
        self.action = models.ResizeAction(self.instance,
                                          OLD_FLAVOR.__dict__,
                                          NEW_FLAVOR.__dict__)

    def _start_mysql(self):
        datastore = Mock(spec=DatastoreVersion)
        datastore.datastore_name = 'mysql'
        datastore.name = 'mysql-5.6'
        datastore.manager = 'mysql'
        config = template.SingleInstanceConfigTemplate(
            datastore, NEW_FLAVOR.__dict__, self.instance.id)
        self.instance.guest.start_db_with_conf_changes(config.render())

    def test_guest_wont_stop_mysql(self):
        self.guest.stop_db(do_not_start_on_reboot=True)\
            .AndRaise(RPCException("Could not stop MySQL!"))

    def test_nova_wont_resize(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID).AndRaise(BadRequest)
        self.server.status = "ACTIVE"
        self.guest.restart()
        self._execute_action()

    def test_nova_resize_timeout(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)

        self.mock.StubOutWithMock(utils, 'poll_until')
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)\
            .AndRaise(PollTimeOut)
        self._execute_action()

    def test_nova_doesnt_change_flavor(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("VERIFY_RESIZE", OLD_FLAVOR_ID)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ACTIVE", OLD_FLAVOR_ID)
        self.guest.restart()
        self._execute_action()

    def test_nova_resize_fails(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("ERROR", OLD_FLAVOR_ID)
        self._execute_action()

    def test_nova_resizes_in_weird_state(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("ACTIVE", NEW_FLAVOR_ID)
        self.guest.restart()
        self._execute_action()

    def test_guest_is_not_okay(self):
        self._stop_db()
        self._nova_resizes_successfully()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.set_datastore_status_to_paused()
        self.instance.datastore_status.status = (
            rd_instance.ServiceStatuses.PAUSED)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)\
            .AndRaise(PollTimeOut)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ACTIVE", OLD_FLAVOR_ID)
        self.guest.restart()
        self._execute_action()

    def test_mysql_is_not_okay(self):
        self._stop_db()
        self._nova_resizes_successfully()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.set_datastore_status_to_paused()
        self.instance.datastore_status.status = (
            rd_instance.ServiceStatuses.SHUTDOWN)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self._start_mysql()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2,
                         time_out=120).AndRaise(PollTimeOut)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ACTIVE", OLD_FLAVOR_ID)
        self.guest.restart()
        self._execute_action()

    def test_confirm_resize_fails(self):
        self._stop_db()
        self._nova_resizes_successfully()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.set_datastore_status_to_paused()
        self.instance.datastore_status.status = (
            rd_instance.ServiceStatuses.RUNNING)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self._start_mysql()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.server.status = "SHUTDOWN"
        self.instance.server.confirm_resize()
        self._execute_action()

    def test_revert_nova_fails(self):
        self._stop_db()
        self._nova_resizes_successfully()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.set_datastore_status_to_paused()
        self.instance.datastore_status.status = (
            rd_instance.ServiceStatuses.PAUSED)
        utils.poll_until(mox.IgnoreArg(),
                         sleep_time=2,
                         time_out=120).AndRaise(PollTimeOut)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ERROR", OLD_FLAVOR_ID)
        self._execute_action()


@test(groups=[GROUP, GROUP + '.migrate'])
class MigrateTests(ResizeTestBase):

    def setUp(self):
        super(MigrateTests, self).setUp()
        self._init()
        self.action = models.MigrateAction(self.instance)

    def _execute_action(self):
        self.instance.update_db(task_status=InstanceTasks.NONE)
        self.mock.ReplayAll()
        self.assertEqual(None, self.action.execute())
        self.mock.VerifyAll()

    def _start_mysql(self):
        self.guest.restart()

    def test_successful_migrate(self):
        self.mock.StubOutWithMock(self.instance.server, 'migrate')
        self._stop_db()
        self.server.migrate(force_host=None)
        self._server_changes_to("VERIFY_RESIZE", NEW_FLAVOR_ID)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.set_datastore_status_to_paused()
        self.instance.datastore_status.status = (
            rd_instance.ServiceStatuses.RUNNING)
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self._start_mysql()
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self.instance.server.confirm_resize()
        self._execute_action()
