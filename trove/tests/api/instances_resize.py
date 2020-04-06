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

from novaclient.exceptions import BadRequest
from novaclient.v2.servers import Server
from unittest import mock

from oslo_messaging._drivers.common import RPCException
from proboscis import test
from testtools import TestCase

from trove.common.exception import PollTimeOut
from trove.common.exception import TroveError
from trove.common import instance as rd_instance
from trove.common import template
from trove.common import utils
from trove.datastore.models import DatastoreVersion
from trove.guestagent import api as guest
from trove.instance.models import DBInstance
from trove.instance.models import InstanceServiceStatus
from trove.instance.tasks import InstanceTasks
from trove.taskmanager import models
from trove.tests.fakes import nova
from trove.tests.unittests import trove_testtools
from trove.tests.util import test_config

GROUP = 'dbaas.api.instances.resize'

OLD_FLAVOR_ID = 1
NEW_FLAVOR_ID = 2
OLD_FLAVOR = nova.FLAVORS.get(OLD_FLAVOR_ID)
NEW_FLAVOR = nova.FLAVORS.get(NEW_FLAVOR_ID)


class ResizeTestBase(TestCase):

    def _init(self):
        self.instance_id = 500
        context = trove_testtools.TroveTestContext(self)
        self.db_info = DBInstance.create(
            name="instance",
            flavor_id=OLD_FLAVOR_ID,
            tenant_id=999,
            volume_size=None,
            datastore_version_id=test_config.dbaas_datastore_version_id,
            task_status=InstanceTasks.RESIZING)
        self.server = mock.MagicMock(spec=Server)
        self.instance = models.BuiltInstanceTasks(
            context,
            self.db_info,
            self.server,
            datastore_status=InstanceServiceStatus.create(
                instance_id=self.db_info.id,
                status=rd_instance.ServiceStatuses.RUNNING))
        self.instance.server.flavor = {'id': OLD_FLAVOR_ID}
        self.guest = mock.MagicMock(spec=guest.API)
        self.instance._guest = self.guest
        self.instance.refresh_compute_server_info = lambda: None
        self.instance._refresh_datastore_status = lambda: None
        self.instance.update_db = mock.Mock()
        self.instance.set_datastore_status_to_paused = mock.Mock()
        self.poll_until_side_effects = []
        self.action = None

    def tearDown(self):
        super(ResizeTestBase, self).tearDown()
        self.db_info.delete()

    def _poll_until(self, *args, **kwargs):
        try:
            effect = self.poll_until_side_effects.pop(0)
        except IndexError:
            effect = None

        if isinstance(effect, Exception):
            raise effect
        elif effect is not None:
            new_status, new_flavor_id = effect
            self.server.status = new_status
            self.instance.server.flavor['id'] = new_flavor_id

    def _datastore_changes_to(self, new_status):
        self.instance.datastore_status.status = new_status


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
        datastore = mock.Mock(spec=DatastoreVersion)
        datastore.datastore_name = 'mysql'
        datastore.name = 'mysql-5.7'
        datastore.manager = 'mysql'
        config = template.SingleInstanceConfigTemplate(
            datastore, NEW_FLAVOR.__dict__, self.instance.id)
        self.instance.guest.start_db_with_conf_changes(config.render())

    def test_guest_wont_stop_mysql(self):
        self.guest.stop_db.side_effect = RPCException("Could not stop MySQL!")
        self.assertRaises(RPCException, self.action.execute)
        self.assertEqual(1, self.guest.stop_db.call_count)
        self.instance.update_db.assert_called_once_with(
            task_status=InstanceTasks.NONE)

    def test_nova_wont_resize(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)
        self.server.resize.side_effect = BadRequest(400)
        self.server.status = "ACTIVE"
        self.assertRaises(BadRequest, self.action.execute)
        self.assertEqual(1, self.guest.stop_db.call_count)
        self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
        self.guest.restart.assert_called_once()
        self.instance.update_db.assert_called_once_with(
            task_status=InstanceTasks.NONE)

    def test_nova_resize_timeout(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)
        self.server.status = "ACTIVE"

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            mock_poll_until.side_effect = [None, PollTimeOut()]
            self.assertRaises(PollTimeOut, self.action.execute)
            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 2
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_nova_doesnt_change_flavor(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                ("VERIFY_RESIZE", OLD_FLAVOR_ID),
                None,
                ("ACTIVE", OLD_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.assertRaisesRegex(TroveError,
                                   "flavor_id=.* and not .*",
                                   self.action.execute)
            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 3
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.guest.reset_configuration.assert_called_once_with(
                mock.ANY)
            self.instance.server.revert_resize.assert_called_once()
            self.guest.restart.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_nova_resize_fails(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("ERROR", OLD_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.assertRaisesRegex(TroveError,
                                   "status=ERROR and not VERIFY_RESIZE",
                                   self.action.execute)

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 2
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_nova_resizes_in_weird_state(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("ACTIVE", NEW_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.assertRaisesRegex(TroveError,
                                   "status=ACTIVE and not VERIFY_RESIZE",
                                   self.action.execute)

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 2
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.guest.restart.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_guest_is_not_okay(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("VERIFY_RESIZE", NEW_FLAVOR_ID),
                None,
                PollTimeOut(),
                ("ACTIVE", OLD_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.instance.set_datastore_status_to_paused.side_effect = (
                lambda: self._datastore_changes_to(
                    rd_instance.ServiceStatuses.PAUSED))

            self.assertRaises(PollTimeOut, self.action.execute)

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 5
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.set_datastore_status_to_paused.assert_called_once()
            self.instance.guest.reset_configuration.assert_called_once_with(
                mock.ANY)
            self.instance.server.revert_resize.assert_called_once()
            self.guest.restart.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_mysql_is_not_okay(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("VERIFY_RESIZE", NEW_FLAVOR_ID),
                PollTimeOut(),
                ("ACTIVE", OLD_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.instance.set_datastore_status_to_paused.side_effect = (
                lambda: self._datastore_changes_to(
                    rd_instance.ServiceStatuses.SHUTDOWN))

            self._start_mysql()
            self.assertRaises(PollTimeOut, self.action.execute)

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 4
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.set_datastore_status_to_paused.assert_called_once()
            self.instance.guest.reset_configuration.assert_called_once_with(
                mock.ANY)
            self.instance.server.revert_resize.assert_called_once()
            self.guest.restart.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_confirm_resize_fails(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("VERIFY_RESIZE", NEW_FLAVOR_ID),
                None,
                None,
                ("SHUTDOWN", NEW_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.instance.set_datastore_status_to_paused.side_effect = (
                lambda: self._datastore_changes_to(
                    rd_instance.ServiceStatuses.RUNNING))
            self.server.confirm_resize.side_effect = BadRequest(400)

            self._start_mysql()
            self.assertRaises(BadRequest, self.action.execute)

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 5
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.set_datastore_status_to_paused.assert_called_once()
            self.instance.server.confirm_resize.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)

    def test_revert_nova_fails(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("VERIFY_RESIZE", NEW_FLAVOR_ID),
                None,
                PollTimeOut(),
                ("ERROR", OLD_FLAVOR_ID)])
            mock_poll_until.side_effect = self._poll_until

            self.instance.set_datastore_status_to_paused.side_effect = (
                lambda: self._datastore_changes_to(
                    rd_instance.ServiceStatuses.PAUSED))

            self.assertRaises(PollTimeOut, self.action.execute)

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 5
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.resize.assert_called_once_with(NEW_FLAVOR_ID)
            self.instance.set_datastore_status_to_paused.assert_called_once()
            self.instance.guest.reset_configuration.assert_called_once_with(
                mock.ANY)
            self.instance.server.revert_resize.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)


@test(groups=[GROUP, GROUP + '.migrate'])
class MigrateTests(ResizeTestBase):

    def setUp(self):
        super(MigrateTests, self).setUp()
        self._init()
        self.action = models.MigrateAction(self.instance)

    def test_successful_migrate(self):
        self._datastore_changes_to(rd_instance.ServiceStatuses.SHUTDOWN)

        with mock.patch.object(utils, 'poll_until') as mock_poll_until:
            self.poll_until_side_effects.extend([
                None,
                ("VERIFY_RESIZE", NEW_FLAVOR_ID),
                None,
                None])
            mock_poll_until.side_effect = self._poll_until

            self.instance.set_datastore_status_to_paused.side_effect = (
                lambda: self._datastore_changes_to(
                    rd_instance.ServiceStatuses.RUNNING))

            self.action.execute()

            expected_calls = [
                mock.call(mock.ANY, sleep_time=2, time_out=120)] * 4
            self.assertEqual(expected_calls, mock_poll_until.call_args_list)
            # Make sure self.poll_until_side_effects is empty
            self.assertFalse(self.poll_until_side_effects)
            self.assertEqual(1, self.guest.stop_db.call_count)
            self.server.migrate.assert_called_once_with(force_host=None)
            self.instance.set_datastore_status_to_paused.assert_called_once()
            self.instance.server.confirm_resize.assert_called_once()
            self.instance.update_db.assert_called_once_with(
                task_status=InstanceTasks.NONE)
