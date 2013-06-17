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

import mox
from testtools import TestCase
from proboscis import test

from novaclient.exceptions import BadRequest
from novaclient.v1_1.servers import Server

from trove.common.exception import PollTimeOut
from trove.common import utils
from trove.common.context import TroveContext
from trove.guestagent import api as guest
from trove.instance.models import DBInstance
from trove.instance.models import ServiceStatuses
from trove.instance.tasks import InstanceTasks
from trove.openstack.common.rpc.common import RPCException
from trove.taskmanager import models as models

GROUP = 'dbaas.api.instances.resize'

OLD_FLAVOR_ID = 1
NEW_FLAVOR_ID = 2


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
            task_status=InstanceTasks.RESIZING)
        self.server = self.mock.CreateMock(Server)
        self.instance = models.BuiltInstanceTasks(context,
                                                  self.db_info,
                                                  self.server,
                                                  service_status="ACTIVE")
        self.instance.server.flavor = {'id': OLD_FLAVOR_ID}
        self.guest = self.mock.CreateMock(guest.API)
        self.instance._guest = self.guest
        self.instance._refresh_compute_server_info = lambda: None
        self.instance._refresh_compute_service_status = lambda: None
        self.mock.StubOutWithMock(self.instance, 'update_db')
        self.mock.StubOutWithMock(self.instance,
                                  '_set_service_status_to_paused')
        self.poll_until_mocked = False
        self.action = None

    def _teardown(self):
        try:
            self.instance.update_db(task_status=InstanceTasks.NONE)
            self.mock.ReplayAll()
            self.assertRaises(Exception, self.action.execute)
            self.mock.VerifyAll()
        finally:
            self.mock.UnsetStubs()
            self.db_info.delete()

    def _stop_db(self, reboot=True):
        self.guest.stop_db(do_not_start_on_reboot=reboot)

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
        self.action = models.ResizeAction(self.instance,
                                          new_flavor_id=NEW_FLAVOR_ID)

    def tearDown(self):
        super(ResizeTests, self).tearDown()
        self._teardown()

    def _start_mysql(self):
        self.instance.guest.start_db_with_conf_changes(None)

    def test_guest_wont_stop_mysql(self):
        self.guest.stop_db(do_not_start_on_reboot=True)\
            .AndRaise(RPCException("Could not stop MySQL!"))

    def test_nova_wont_resize(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID).AndRaise(BadRequest)
        self.server.status = "ACTIVE"
        self.guest.restart()

    def test_nova_resize_timeout(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)

        self.mock.StubOutWithMock(utils, 'poll_until')
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)\
            .AndRaise(PollTimeOut)

    def test_nova_doesnt_change_flavor(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("VERIFY_RESIZE", OLD_FLAVOR_ID)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ACTIVE", OLD_FLAVOR_ID)
        self.guest.restart()

    def test_nova_resize_fails(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("ERROR", OLD_FLAVOR_ID)

    def test_nova_resizes_in_weird_state(self):
        self._stop_db()
        self.server.resize(NEW_FLAVOR_ID)
        self._server_changes_to("ACTIVE", NEW_FLAVOR_ID)
        self.guest.restart()

    def test_guest_is_not_okay(self):
        self._stop_db()
        self._nova_resizes_successfully()
        self.instance._set_service_status_to_paused()
        self.instance.service_status = ServiceStatuses.PAUSED
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)\
            .AndRaise(PollTimeOut)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ACTIVE", OLD_FLAVOR_ID)
        self.guest.restart()

    def test_mysql_is_not_okay(self):
        self._stop_db()
        self._nova_resizes_successfully()
        self.instance._set_service_status_to_paused()
        self.instance.service_status = ServiceStatuses.SHUTDOWN
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self._start_mysql()
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ACTIVE", OLD_FLAVOR_ID)
        self.guest.restart()

    def test_confirm_resize_fails(self):
        self._stop_db()
        self._nova_resizes_successfully()
        self.instance._set_service_status_to_paused()
        self.instance.service_status = ServiceStatuses.RUNNING
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self._start_mysql()
        self.server.status = "SHUTDOWN"
        self.instance.server.confirm_resize()

    def test_revert_nova_fails(self):
        self._stop_db()
        self._nova_resizes_successfully()
        self.instance._set_service_status_to_paused()
        self.instance.service_status = ServiceStatuses.PAUSED
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)\
            .AndRaise(PollTimeOut)
        self.instance.guest.reset_configuration(mox.IgnoreArg())
        self.instance.server.revert_resize()
        self._server_changes_to("ERROR", OLD_FLAVOR_ID)


@test(groups=[GROUP, GROUP + '.migrate'])
class MigrateTests(ResizeTestBase):

    def setUp(self):
        super(MigrateTests, self).setUp()
        self._init()
        self.action = models.MigrateAction(self.instance)

    def tearDown(self):
        super(MigrateTests, self).tearDown()
        try:
            self.instance.update_db(task_status=InstanceTasks.NONE)
            self.mock.ReplayAll()
            self.assertEqual(None, self.action.execute())
            self.mock.VerifyAll()
        finally:
            self.mock.UnsetStubs()
            self.db_info.delete()

    def _start_mysql(self):
        self.guest.restart()

    def test_successful_migrate(self):
        self._stop_db()
        self.server.migrate()
        self._server_changes_to("VERIFY_RESIZE", NEW_FLAVOR_ID)
        self.instance._set_service_status_to_paused()
        self.instance.service_status = ServiceStatuses.RUNNING
        utils.poll_until(mox.IgnoreArg(), sleep_time=2, time_out=120)
        self._start_mysql()
        self.instance.server.confirm_resize()
