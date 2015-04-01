#    Copyright 2012 OpenStack Foundation
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
import datetime

import testtools
from mock import Mock, MagicMock, patch
from testtools.matchers import Equals, Is
from cinderclient import exceptions as cinder_exceptions
from novaclient import exceptions as nova_exceptions
import novaclient.v2.servers
import novaclient.v2.flavors
import cinderclient.v2.client as cinderclient
from oslo.utils import timeutils
import trove.backup.models
import trove.common.context
from trove.datastore import models as datastore_models
import trove.db.models
from trove.taskmanager import models as taskmanager_models
import trove.guestagent.api
from trove.backup import models as backup_models
from trove.backup import state
from trove.common import remote
from trove.common.exception import GuestError
from trove.common.exception import PollTimeOut
from trove.common.exception import TroveError
from trove.common.exception import MalformedSecurityGroupRuleError
from trove.common.instance import ServiceStatuses
from trove.extensions.mysql import models as mysql_models
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import InstanceStatus
from trove.instance.models import DBInstance
from trove.instance.tasks import InstanceTasks
from trove.tests.unittests.util import util
from trove.common import utils
from trove import rpc
from swiftclient.client import ClientException
from tempfile import NamedTemporaryFile
import os
import trove.common.template as template
import uuid

INST_ID = 'dbinst-id-1'
VOLUME_ID = 'volume-id-1'


class FakeOptGroup(object):
    def __init__(self, tcp_ports=['3306', '3301-3307'],
                 udp_ports=[]):
        self.tcp_ports = tcp_ports
        self.udp_ports = udp_ports


class fake_Server:
    def __init__(self):
        self.id = None
        self.name = None
        self.image_id = None
        self.flavor_id = None
        self.files = None
        self.userdata = None
        self.security_groups = None
        self.block_device_mapping = None
        self.status = 'ACTIVE'


class fake_ServerManager:
    def create(self, name, image_id, flavor_id, files, userdata,
               security_groups, block_device_mapping, availability_zone=None,
               nics=None, config_drive=False):
        server = fake_Server()
        server.id = "server_id"
        server.name = name
        server.image_id = image_id
        server.flavor_id = flavor_id
        server.files = files
        server.userdata = userdata
        server.security_groups = security_groups
        server.block_device_mapping = block_device_mapping
        server.availability_zone = availability_zone
        server.nics = nics
        return server


class fake_nova_client:
    def __init__(self):
        self.servers = fake_ServerManager()


class fake_InstanceServiceStatus(object):

    _instance = None

    def __init__(self):
        self.deleted = False
        self.status = None
        pass

    def set_status(self, status):
        self.status = status
        pass

    def get_status(self):
        return self.status

    @classmethod
    def find_by(cls, **kwargs):
        if not cls._instance:
            cls._instance = fake_InstanceServiceStatus()
        return cls._instance

    def save(self):
        pass

    def delete(self):
        self.deleted = True
        pass

    def is_deleted(self):
        return self.deleted


class fake_DBInstance(object):

    _instance = None

    def __init__(self):
        self.deleted = False
        pass

    @classmethod
    def find_by(cls, **kwargs):
        if not cls._instance:
            cls._instance = fake_DBInstance()
        return cls._instance

    def set_task_status(self, status):
        self.status = status
        pass

    def get_task_status(self):
        return self.status

    def save(self):
        pass

    def delete(self):
        self.deleted = True
        pass

    def is_deleted(self):
        return self.deleted


class FreshInstanceTasksTest(testtools.TestCase):
    def setUp(self):
        super(FreshInstanceTasksTest, self).setUp()
        mock_instance = patch('trove.instance.models.FreshInstance')
        mock_instance.start()
        self.addCleanup(mock_instance.stop)
        mock_instance.id = Mock(return_value='instance_id')
        mock_instance.tenant_id = Mock(return_value="tenant_id")
        mock_instance.hostname = Mock(return_value="hostname")
        mock_instance.name = Mock(return_value='name')
        mock_instance.nova_client = Mock(
            return_value=fake_nova_client())
        mock_datastore_v = patch(
            'trove.datastore.models.DatastoreVersion')
        mock_datastore_v.start()
        self.addCleanup(mock_datastore_v.stop)
        mock_datastore = patch(
            'trove.datastore.models.Datastore')
        mock_datastore.start()
        self.addCleanup(mock_datastore.stop)

        taskmanager_models.FreshInstanceTasks.nova_client = fake_nova_client()
        self.orig_ISS_find_by = InstanceServiceStatus.find_by
        self.orig_DBI_find_by = DBInstance.find_by
        self.userdata = "hello moto"
        self.guestconfig_content = "guest config"
        with NamedTemporaryFile(suffix=".cloudinit", delete=False) as f:
            self.cloudinit = f.name
            f.write(self.userdata)
        with NamedTemporaryFile(delete=False) as f:
            self.guestconfig = f.name
            f.write(self.guestconfig_content)
        self.freshinstancetasks = taskmanager_models.FreshInstanceTasks(
            None, Mock(), None, None)

    def tearDown(self):
        super(FreshInstanceTasksTest, self).tearDown()
        os.remove(self.cloudinit)
        os.remove(self.guestconfig)
        InstanceServiceStatus.find_by = self.orig_ISS_find_by
        DBInstance.find_by = self.orig_DBI_find_by

    @patch('trove.taskmanager.models.CONF')
    def test_create_instance_userdata(self, mock_conf):
        cloudinit_location = os.path.dirname(self.cloudinit)
        datastore_manager = os.path.splitext(os.path.basename(self.
                                                              cloudinit))[0]

        def fake_conf_getter(*args, **kwargs):
            if args[0] == 'cloudinit_location':
                return cloudinit_location
            else:
                return ''
        mock_conf.get.side_effect = fake_conf_getter

        server = self.freshinstancetasks._create_server(
            None, None, None, datastore_manager, None, None, None)
        self.assertEqual(server.userdata, self.userdata)

    @patch('trove.taskmanager.models.CONF')
    def test_create_instance_guestconfig(self, mock_conf):
        def fake_conf_getter(*args, **kwargs):
            if args[0] == 'guest_config':
                return self.guestconfig
            if args[0] == 'guest_info':
                return 'guest_info.conf'
            if args[0] == 'injected_config_location':
                return '/etc/trove/conf.d'
            else:
                return ''

        mock_conf.get.side_effect = fake_conf_getter
        # execute
        files = self.freshinstancetasks._get_injected_files("test")
        # verify
        self.assertTrue(
            '/etc/trove/conf.d/guest_info.conf' in files)
        self.assertTrue(
            '/etc/trove/conf.d/trove-guestagent.conf' in files)
        self.assertEqual(
            files['/etc/trove/conf.d/trove-guestagent.conf'],
            self.guestconfig_content)

    @patch('trove.taskmanager.models.CONF')
    def test_create_instance_guestconfig_compat(self, mock_conf):
        def fake_conf_getter(*args, **kwargs):
            if args[0] == 'guest_config':
                return self.guestconfig
            if args[0] == 'guest_info':
                return '/etc/guest_info'
            if args[0] == 'injected_config_location':
                return '/etc'
            else:
                return ''

        mock_conf.get.side_effect = fake_conf_getter
        # execute
        files = self.freshinstancetasks._get_injected_files("test")
        # verify
        self.assertTrue(
            '/etc/guest_info' in files)
        self.assertTrue(
            '/etc/trove-guestagent.conf' in files)
        self.assertEqual(
            files['/etc/trove-guestagent.conf'],
            self.guestconfig_content)

    @patch('trove.taskmanager.models.CONF')
    def test_create_instance_with_az_kwarg(self, mock_conf):
        mock_conf.get.return_value = ''
        # execute
        server = self.freshinstancetasks._create_server(
            None, None, None, None, None, availability_zone='nova', nics=None)
        # verify
        self.assertIsNotNone(server)

    @patch('trove.taskmanager.models.CONF')
    def test_create_instance_with_az(self, mock_conf):
        mock_conf.get.return_value = ''
        # execute
        server = self.freshinstancetasks._create_server(
            None, None, None, None, None, 'nova', None)
        # verify
        self.assertIsNotNone(server)

    @patch('trove.taskmanager.models.CONF')
    def test_create_instance_with_az_none(self, mock_conf):
        mock_conf.get.return_value = ''
        # execute
        server = self.freshinstancetasks._create_server(
            None, None, None, None, None, None, None)
        # verify
        self.assertIsNotNone(server)

    @patch('trove.taskmanager.models.CONF')
    def test_update_status_of_intance_failure(self, mock_conf):
        mock_conf.get.return_value = ''
        InstanceServiceStatus.find_by = Mock(
            return_value=fake_InstanceServiceStatus.find_by())
        DBInstance.find_by = Mock(
            return_value=fake_DBInstance.find_by())
        self.freshinstancetasks.update_statuses_on_time_out()
        self.assertEqual(fake_InstanceServiceStatus.find_by().get_status(),
                         ServiceStatuses.FAILED_TIMEOUT_GUESTAGENT)
        self.assertEqual(fake_DBInstance.find_by().get_task_status(),
                         InstanceTasks.BUILDING_ERROR_TIMEOUT_GA)

    def test_create_sg_rules_success(self):
        datastore_manager = 'mysql'
        taskmanager_models.SecurityGroup.create_for_instance = (
            Mock(return_value={'id': uuid.uuid4(),
                               'name': uuid.uuid4()}))
        taskmanager_models.CONF.get = Mock(return_value=FakeOptGroup())
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = (
            Mock())
        self.freshinstancetasks._create_secgroup(datastore_manager)
        self.assertEqual(2, taskmanager_models.SecurityGroupRule.
                         create_sec_group_rule.call_count)

    def test_create_sg_rules_format_exception_raised(self):
        datastore_manager = 'mysql'
        taskmanager_models.SecurityGroup.create_for_instance = (
            Mock(return_value={'id': uuid.uuid4(),
                               'name': uuid.uuid4()}))
        taskmanager_models.CONF.get = Mock(
            return_value=FakeOptGroup(tcp_ports=['3306', '-3306']))
        self.freshinstancetasks.update_db = Mock()
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = (
            Mock())
        self.assertRaises(MalformedSecurityGroupRuleError,
                          self.freshinstancetasks._create_secgroup,
                          datastore_manager)

    def test_create_sg_rules_greater_than_exception_raised(self):
        datastore_manager = 'mysql'
        taskmanager_models.SecurityGroup.create_for_instance = (
            Mock(return_value={'id': uuid.uuid4(),
                               'name': uuid.uuid4()}))
        taskmanager_models.CONF.get = Mock(
            return_value=FakeOptGroup(tcp_ports=['3306', '33060-3306']))
        self.freshinstancetasks.update_db = Mock()
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = (
            Mock())
        self.assertRaises(MalformedSecurityGroupRuleError,
                          self.freshinstancetasks._create_secgroup,
                          datastore_manager)

    def test_create_sg_rules_success_with_duplicated_port_or_range(self):
        datastore_manager = 'mysql'
        taskmanager_models.SecurityGroup.create_for_instance = (
            Mock(return_value={'id': uuid.uuid4(),
                               'name': uuid.uuid4()}))
        taskmanager_models.CONF.get = Mock(
            return_value=FakeOptGroup(
                tcp_ports=['3306', '3306', '3306-3307', '3306-3307']))
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = (
            Mock())
        self.freshinstancetasks.update_db = Mock()
        self.freshinstancetasks._create_secgroup(datastore_manager)
        self.assertEqual(2, taskmanager_models.SecurityGroupRule.
                         create_sec_group_rule.call_count)

    def test_create_sg_rules_exception_with_malformed_ports_or_range(self):
        datastore_manager = 'mysql'
        taskmanager_models.SecurityGroup.create_for_instance = (
            Mock(return_value={'id': uuid.uuid4(),
                               'name': uuid.uuid4()}))
        taskmanager_models.CONF.get = Mock(
            return_value=FakeOptGroup(tcp_ports=['A', 'B-C']))
        self.freshinstancetasks.update_db = Mock()
        self.assertRaises(MalformedSecurityGroupRuleError,
                          self.freshinstancetasks._create_secgroup,
                          datastore_manager)


class ResizeVolumeTest(testtools.TestCase):
    def setUp(self):
        super(ResizeVolumeTest, self).setUp()
        utils.poll_until = Mock()
        timeutils.isotime = Mock()
        self.instance = Mock()
        self.old_vol_size = 1
        self.new_vol_size = 2
        self.action = taskmanager_models.ResizeVolumeAction(self.instance,
                                                            self.old_vol_size,
                                                            self.new_vol_size)

        class FakeGroup():
            def __init__(self):
                self.mount_point = 'var/lib/mysql'
                self.device_path = '/dev/vdb'
        taskmanager_models.CONF.get = Mock(return_value=FakeGroup())

    def tearDown(self):
        super(ResizeVolumeTest, self).tearDown()

    def test_resize_volume_unmount_exception(self):
        self.instance.guest.unmount_volume = Mock(
            side_effect=GuestError("test exception"))
        self.assertRaises(GuestError,
                          self.action._unmount_volume,
                          recover_func=self.action._recover_restart)
        self.assertEqual(1, self.instance.restart.call_count)
        self.instance.guest.unmount_volume.side_effect = None
        self.instance.reset_mock()

    def test_resize_volume_detach_exception(self):
        self.instance.nova_client.volumes.delete_server_volume = Mock(
            side_effect=nova_exceptions.ClientException("test exception"))
        self.assertRaises(nova_exceptions.ClientException,
                          self.action._detach_volume,
                          recover_func=self.action._recover_mount_restart)
        self.assertEqual(1, self.instance.guest.mount_volume.call_count)
        self.assertEqual(1, self.instance.restart.call_count)
        self.instance.nova_client.volumes.delete_server_volume.side_effect = (
            None)
        self.instance.reset_mock()

    def test_resize_volume_extend_exception(self):
        self.instance.volume_client.volumes.extend = Mock(
            side_effect=cinder_exceptions.ClientException("test exception"))
        self.assertRaises(cinder_exceptions.ClientException,
                          self.action._extend,
                          recover_func=self.action._recover_full)
        attach_count = (
            self.instance.nova_client.volumes.create_server_volume.call_count)
        self.assertEqual(1, attach_count)
        self.assertEqual(1, self.instance.guest.mount_volume.call_count)
        self.assertEqual(1, self.instance.restart.call_count)
        self.instance.volume_client.volumes.extend.side_effect = None
        self.instance.reset_mock()

    def test_resize_volume_verify_extend_no_volume(self):
        self.instance.volume_client.volumes.get = Mock(
            return_value=None)
        self.assertRaises(cinder_exceptions.ClientException,
                          self.action._verify_extend)
        self.instance.reset_mock()

    def test_resize_volume_poll_timeout(self):
        utils.poll_until = Mock(side_effect=PollTimeOut)
        self.assertRaises(PollTimeOut, self.action._verify_extend)
        self.assertEqual(2, self.instance.volume_client.volumes.get.call_count)
        utils.poll_until.side_effect = None
        self.instance.reset_mock()

    def test_resize_volume_active_server_succeeds(self):
        server = Mock(status=InstanceStatus.ACTIVE)
        self.instance.attach_mock(server, 'server')
        self.action.execute()
        self.assertEqual(1, self.instance.guest.stop_db.call_count)
        self.assertEqual(1, self.instance.guest.unmount_volume.call_count)
        detach_count = (
            self.instance.nova_client.volumes.delete_server_volume.call_count)
        self.assertEqual(1, detach_count)
        extend_count = self.instance.volume_client.volumes.extend.call_count
        self.assertEqual(1, extend_count)
        attach_count = (
            self.instance.nova_client.volumes.create_server_volume.call_count)
        self.assertEqual(1, attach_count)
        self.assertEqual(1, self.instance.guest.resize_fs.call_count)
        self.assertEqual(1, self.instance.guest.mount_volume.call_count)
        self.assertEqual(1, self.instance.restart.call_count)
        self.instance.reset_mock()

    def test_resize_volume_server_error_fails(self):
        server = Mock(status=InstanceStatus.ERROR)
        self.instance.attach_mock(server, 'server')
        self.assertRaises(TroveError, self.action.execute)
        self.instance.reset_mock()


class BuiltInstanceTasksTest(testtools.TestCase):

    def get_inst_service_status(self, status_id, statuses):
        answers = []
        for i, status in enumerate(statuses):
            inst_svc_status = InstanceServiceStatus(status,
                                                    id="%s-%s" % (status_id,
                                                                  i))
            inst_svc_status.save = MagicMock(return_value=None)
            answers.append(inst_svc_status)
        return answers

    def _stub_volume_client(self):
        self.instance_task._volume_client = MagicMock(spec=cinderclient.Client)
        stub_volume_mgr = MagicMock(spec=cinderclient.volumes.VolumeManager)
        self.instance_task.volume_client.volumes = stub_volume_mgr
        stub_volume_mgr.extend = MagicMock(return_value=None)
        stub_new_volume = cinderclient.volumes.Volume(
            stub_volume_mgr, {'status': 'available', 'size': 2}, True)
        stub_volume_mgr.get = MagicMock(return_value=stub_new_volume)
        stub_volume_mgr.attach = MagicMock(return_value=None)

    def setUp(self):
        super(BuiltInstanceTasksTest, self).setUp()
        self.new_flavor = {'id': 8, 'ram': 768, 'name': 'bigger_flavor'}
        stub_nova_server = MagicMock()
        rpc.get_notifier = MagicMock()
        rpc.get_client = MagicMock()
        db_instance = DBInstance(InstanceTasks.NONE,
                                 id=INST_ID,
                                 name='resize-inst-name',
                                 datastore_version_id='1',
                                 datastore_id='id-1',
                                 flavor_id='6',
                                 manager='mysql',
                                 created=datetime.datetime.utcnow(),
                                 updated=datetime.datetime.utcnow(),
                                 compute_instance_id='computeinst-id-1',
                                 tenant_id='testresize-tenant-id',
                                 volume_size='1',
                                 volume_id=VOLUME_ID)

        # this is used during the final check of whether the resize successful
        db_instance.server_status = 'ACTIVE'
        self.db_instance = db_instance
        datastore_models.DatastoreVersion.load_by_uuid = MagicMock(
            return_value=datastore_models.DatastoreVersion(db_instance))
        datastore_models.Datastore.load = MagicMock(
            return_value=datastore_models.Datastore(db_instance))

        self.instance_task = taskmanager_models.BuiltInstanceTasks(
            trove.common.context.TroveContext(),
            db_instance,
            stub_nova_server,
            InstanceServiceStatus(ServiceStatuses.RUNNING,
                                  id='inst-stat-id-0'))

        self.instance_task._guest = MagicMock(spec=trove.guestagent.api.API)
        self.instance_task._nova_client = MagicMock(
            spec=novaclient.v2.Client)
        self.stub_server_mgr = MagicMock(
            spec=novaclient.v2.servers.ServerManager)
        self.stub_running_server = MagicMock(
            spec=novaclient.v2.servers.Server)
        self.stub_running_server.status = 'ACTIVE'
        self.stub_running_server.flavor = {'id': 6, 'ram': 512}
        self.stub_verifying_server = MagicMock(
            spec=novaclient.v2.servers.Server)
        self.stub_verifying_server.status = 'VERIFY_RESIZE'
        self.stub_verifying_server.flavor = {'id': 8, 'ram': 768}
        self.stub_server_mgr.get = MagicMock(
            return_value=self.stub_verifying_server)
        self.instance_task._nova_client.servers = self.stub_server_mgr
        stub_flavor_manager = MagicMock(
            spec=novaclient.v2.flavors.FlavorManager)
        self.instance_task._nova_client.flavors = stub_flavor_manager

        nova_flavor = novaclient.v2.flavors.Flavor(stub_flavor_manager,
                                                   self.new_flavor,
                                                   True)
        stub_flavor_manager.get = MagicMock(return_value=nova_flavor)

        answers = (status for status in
                   self.get_inst_service_status('inst_stat-id',
                                                [ServiceStatuses.SHUTDOWN,
                                                 ServiceStatuses.RUNNING,
                                                 ServiceStatuses.RUNNING,
                                                 ServiceStatuses.RUNNING]))

        def side_effect_func(*args, **kwargs):
            if 'instance_id' in kwargs:
                return answers.next()
            elif ('id' in kwargs and 'deleted' in kwargs
                  and not kwargs['deleted']):
                return db_instance
            else:
                return MagicMock()
        trove.db.models.DatabaseModelBase.find_by = MagicMock(
            side_effect=side_effect_func)

        template.SingleInstanceConfigTemplate = MagicMock(
            spec=template.SingleInstanceConfigTemplate)
        db_instance.save = MagicMock(return_value=None)
        trove.backup.models.Backup.running = MagicMock(return_value=None)

        if 'volume' in self._testMethodName:
            self._stub_volume_client()

    def tearDown(self):
        super(BuiltInstanceTasksTest, self).tearDown()

    def test_resize_flavor(self):
        orig_server = self.instance_task.server
        self.instance_task.resize_flavor({'id': 1, 'ram': 512},
                                         self.new_flavor)
        # verify
        self.assertIsNot(self.instance_task.server, orig_server)
        self.instance_task._guest.stop_db.assert_any_call(
            do_not_start_on_reboot=True)
        orig_server.resize.assert_any_call(self.new_flavor['id'])
        self.assertThat(self.db_instance.task_status, Is(InstanceTasks.NONE))
        self.assertEqual(self.stub_server_mgr.get.call_count, 1)
        self.assertThat(self.db_instance.flavor_id, Is(self.new_flavor['id']))

    def test_resize_flavor_resize_failure(self):
        orig_server = self.instance_task.server
        self.stub_verifying_server.status = 'ERROR'
        with patch.object(self.instance_task._nova_client.servers, 'get',
                          return_value=self.stub_verifying_server):
            # execute
            self.assertRaises(TroveError, self.instance_task.resize_flavor,
                              {'id': 1, 'ram': 512}, self.new_flavor)
            # verify
            self.assertTrue(self.stub_server_mgr.get.called)
            self.assertIs(self.instance_task.server,
                          self.stub_verifying_server)
            self.instance_task._guest.stop_db.assert_any_call(
                do_not_start_on_reboot=True)
            orig_server.resize.assert_any_call(self.new_flavor['id'])
            self.assertThat(self.db_instance.task_status,
                            Is(InstanceTasks.NONE))
            self.assertThat(self.db_instance.flavor_id, Is('6'))

    @patch.object(utils, 'poll_until')
    def test_reboot(self, mock_poll):
        self.instance_task.datastore_status_matches = Mock(return_value=True)
        self.instance_task._refresh_datastore_status = Mock()
        self.instance_task.server.reboot = Mock()
        self.instance_task.set_datastore_status_to_paused = Mock()
        self.instance_task.reboot()
        self.instance_task._guest.stop_db.assert_any_call()
        self.instance_task._refresh_datastore_status.assert_any_call()
        self.instance_task.server.reboot.assert_any_call()
        self.instance_task.set_datastore_status_to_paused.assert_any_call()

    @patch.object(utils, 'poll_until')
    def test_reboot_datastore_not_ready(self, mock_poll):
        self.instance_task.datastore_status_matches = Mock(return_value=False)
        self.instance_task._refresh_datastore_status = Mock()
        self.instance_task.server.reboot = Mock()
        self.instance_task.set_datastore_status_to_paused = Mock()
        self.instance_task.reboot()
        self.instance_task._guest.stop_db.assert_any_call()
        self.instance_task._refresh_datastore_status.assert_any_call()
        assert not self.instance_task.server.reboot.called
        assert not self.instance_task.set_datastore_status_to_paused.called


class BackupTasksTest(testtools.TestCase):
    def setUp(self):
        super(BackupTasksTest, self).setUp()
        self.backup = backup_models.DBBackup()
        self.backup.id = 'backup_id'
        self.backup.name = 'backup_test',
        self.backup.description = 'test desc'
        self.backup.location = 'http://xxx/z_CLOUD/12e48.xbstream.gz'
        self.backup.instance_id = 'instance id'
        self.backup.created = 'yesterday'
        self.backup.updated = 'today'
        self.backup.size = 2.0
        self.backup.state = state.BackupState.NEW
        self.container_content = (None,
                                  [{'name': 'first'},
                                   {'name': 'second'},
                                   {'name': 'third'}])
        backup_models.Backup.delete = MagicMock(return_value=None)
        backup_models.Backup.get_by_id = MagicMock(return_value=self.backup)
        backup_models.DBBackup.save = MagicMock(return_value=self.backup)
        self.backup.delete = MagicMock(return_value=None)
        self.swift_client = MagicMock()
        remote.create_swift_client = MagicMock(return_value=self.swift_client)

        self.swift_client.head_container = MagicMock(
            side_effect=ClientException("foo"))
        self.swift_client.head_object = MagicMock(
            side_effect=ClientException("foo"))
        self.swift_client.get_container = MagicMock(
            return_value=self.container_content)
        self.swift_client.delete_object = MagicMock(return_value=None)
        self.swift_client.delete_container = MagicMock(return_value=None)

    def tearDown(self):
        super(BackupTasksTest, self).tearDown()

    def test_delete_backup_nolocation(self):
        self.backup.location = ''
        taskmanager_models.BackupTasks.delete_backup('dummy context',
                                                     self.backup.id)
        self.backup.delete.assert_any_call()

    def test_delete_backup_fail_delete_manifest(self):
        with patch.object(self.swift_client, 'delete_object',
                          side_effect=ClientException("foo")):
            with patch.object(self.swift_client, 'head_object',
                              return_value={}):
                self.assertRaises(
                    TroveError,
                    taskmanager_models.BackupTasks.delete_backup,
                    'dummy context', self.backup.id)
                self.assertFalse(backup_models.Backup.delete.called)
                self.assertEqual(
                    state.BackupState.DELETE_FAILED,
                    self.backup.state,
                    "backup should be in DELETE_FAILED status")

    def test_delete_backup_fail_delete_segment(self):
        with patch.object(self.swift_client, 'delete_object',
                          side_effect=ClientException("foo")):
            self.assertRaises(
                TroveError,
                taskmanager_models.BackupTasks.delete_backup,
                'dummy context', self.backup.id)
            self.assertFalse(backup_models.Backup.delete.called)
            self.assertEqual(
                state.BackupState.DELETE_FAILED,
                self.backup.state,
                "backup should be in DELETE_FAILED status")

    def test_parse_manifest(self):
        manifest = 'container/prefix'
        cont, prefix = taskmanager_models.BackupTasks._parse_manifest(manifest)
        self.assertEqual(cont, 'container')
        self.assertEqual(prefix, 'prefix')

    def test_parse_manifest_bad(self):
        manifest = 'bad_prefix'
        cont, prefix = taskmanager_models.BackupTasks._parse_manifest(manifest)
        self.assertEqual(cont, None)
        self.assertEqual(prefix, None)

    def test_parse_manifest_long(self):
        manifest = 'container/long/path/to/prefix'
        cont, prefix = taskmanager_models.BackupTasks._parse_manifest(manifest)
        self.assertEqual(cont, 'container')
        self.assertEqual(prefix, 'long/path/to/prefix')

    def test_parse_manifest_short(self):
        manifest = 'container/'
        cont, prefix = taskmanager_models.BackupTasks._parse_manifest(manifest)
        self.assertEqual(cont, 'container')
        self.assertEqual(prefix, '')


class NotifyMixinTest(testtools.TestCase):
    def test_get_service_id(self):
        id_map = {
            'mysql': '123',
            'percona': 'abc'
        }
        mixin = taskmanager_models.NotifyMixin()
        self.assertThat(mixin._get_service_id('mysql', id_map), Equals('123'))

    def test_get_service_id_unknown(self):
        id_map = {
            'mysql': '123',
            'percona': 'abc'
        }
        transformer = taskmanager_models.NotifyMixin()
        self.assertThat(transformer._get_service_id('m0ng0', id_map),
                        Equals('unknown-service-id-error'))


class RootReportTest(testtools.TestCase):

    def setUp(self):
        super(RootReportTest, self).setUp()
        util.init_db()

    def tearDown(self):
        super(RootReportTest, self).tearDown()

    def test_report_root_first_time(self):
        report = mysql_models.RootHistory.create(
            None, utils.generate_uuid(), 'root')
        self.assertIsNotNone(report)

    def test_report_root_double_create(self):
        uuid = utils.generate_uuid()
        history = mysql_models.RootHistory(uuid, 'root').save()
        mysql_models.RootHistory.load = Mock(return_value=history)
        report = mysql_models.RootHistory.create(
            None, uuid, 'root')
        self.assertTrue(mysql_models.RootHistory.load.called)
        self.assertEqual(history.user, report.user)
        self.assertEqual(history.id, report.id)
