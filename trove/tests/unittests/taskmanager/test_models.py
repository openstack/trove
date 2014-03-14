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
from mock import Mock
from testtools.matchers import Equals, Is
from mockito import mock, when, unstub, any, verify, never
from cinderclient import exceptions as cinder_exceptions
import novaclient.v1_1.servers
import novaclient.v1_1.flavors
import cinderclient.v2.client as cinderclient
import trove.backup.models
import trove.common.context
from trove.datastore import models as datastore_models
import trove.db.models
from trove.taskmanager import models as taskmanager_models
import trove.guestagent.api
from trove.backup import models as backup_models
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
from trove.openstack.common import timeutils
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
               nics=None):
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

        when(taskmanager_models.FreshInstanceTasks).id().thenReturn(
            "instance_id")
        when(taskmanager_models.FreshInstanceTasks).tenant_id().thenReturn(
            "tenant_id")
        when(taskmanager_models.FreshInstanceTasks).hostname().thenReturn(
            "hostname")
        when(taskmanager_models.FreshInstanceTasks).name().thenReturn(
            'name')
        when(datastore_models.
             DatastoreVersion).load(any(), any()).thenReturn(mock())
        when(datastore_models.
             DatastoreVersion).load_by_uuid(any()).thenReturn(mock())
        when(datastore_models.
             Datastore).load(any()).thenReturn(mock())
        taskmanager_models.FreshInstanceTasks.nova_client = fake_nova_client()
        taskmanager_models.CONF = mock()
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
            None, mock(), None, None)

    def tearDown(self):
        super(FreshInstanceTasksTest, self).tearDown()
        os.remove(self.cloudinit)
        os.remove(self.guestconfig)
        InstanceServiceStatus.find_by = self.orig_ISS_find_by
        DBInstance.find_by = self.orig_DBI_find_by
        unstub()

    def test_create_instance_userdata(self):
        when(taskmanager_models.CONF).get(any()).thenReturn('')
        cloudinit_location = os.path.dirname(self.cloudinit)
        datastore_manager = os.path.splitext(os.path.basename(self.
                                                              cloudinit))[0]
        when(taskmanager_models.CONF).get("cloudinit_location").thenReturn(
            cloudinit_location)
        server = self.freshinstancetasks._create_server(
            None, None, None, datastore_manager, None, None, None)
        self.assertEqual(server.userdata, self.userdata)

    def test_create_instance_guestconfig(self):
        when(taskmanager_models.CONF).get(any()).thenReturn('')
        when(taskmanager_models.CONF).get("guest_config").thenReturn(
            self.guestconfig)
        server = self.freshinstancetasks._create_server(
            None, None, None, "test", None, None, None)
        self.assertTrue('/etc/trove-guestagent.conf' in server.files)
        self.assertEqual(server.files['/etc/trove-guestagent.conf'],
                         self.guestconfig_content)

    def test_create_instance_with_az_kwarg(self):
        when(taskmanager_models.CONF).get(any()).thenReturn('')
        server = self.freshinstancetasks._create_server(
            None, None, None, None, None, availability_zone='nova', nics=None)

        self.assertIsNotNone(server)

    def test_create_instance_with_az(self):
        when(taskmanager_models.CONF).get(any()).thenReturn('')
        server = self.freshinstancetasks._create_server(
            None, None, None, None, None, 'nova', None)

        self.assertIsNotNone(server)

    def test_create_instance_with_az_none(self):
        when(taskmanager_models.CONF).get(any()).thenReturn('')
        server = self.freshinstancetasks._create_server(
            None, None, None, None, None, None, None)

        self.assertIsNotNone(server)

    def test_update_status_of_intance_failure(self):

        InstanceServiceStatus.find_by = Mock(
            return_value=fake_InstanceServiceStatus.find_by())
        DBInstance.find_by = Mock(return_value=fake_DBInstance.find_by())
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
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = Mock()
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
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = Mock()
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
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = Mock()
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
        taskmanager_models.SecurityGroupRule.create_sec_group_rule = Mock()
        self.freshinstancetasks.update_db = Mock()
        self.freshinstancetasks._create_secgroup(datastore_manager)
        self.assertEqual(2, taskmanager_models.SecurityGroupRule.
                         create_sec_group_rule.call_count)

    def test_create_sg_rules_exception_with_malformed_ports_or_range(self):
        datastore_manager = 'mysql'
        taskmanager_models.SecurityGroup.create_for_instance = (
            Mock(return_value={'id': uuid.uuid4(), 'name': uuid.uuid4()}))
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
        self.instance.volume_client.volumes.detach = Mock(
            side_effect=cinder_exceptions.ClientException("test exception"))
        self.assertRaises(cinder_exceptions.ClientException,
                          self.action._detach_volume,
                          recover_func=self.action._recover_mount_restart)
        self.assertEqual(1, self.instance.guest.mount_volume.call_count)
        self.assertEqual(1, self.instance.restart.call_count)
        self.instance.volume_client.volumes.detach.side_effect = None
        self.instance.reset_mock()

    def test_resize_volume_extend_exception(self):
        self.instance.volume_client.volumes.extend = Mock(
            side_effect=cinder_exceptions.ClientException("test exception"))
        self.assertRaises(cinder_exceptions.ClientException,
                          self.action._extend,
                          recover_func=self.action._recover_full)
        attach_count = self.instance.volume_client.volumes.attach.call_count
        self.assertEqual(1, attach_count)
        self.assertEqual(1, self.instance.guest.mount_volume.call_count)
        self.assertEqual(1, self.instance.restart.call_count)
        self.instance.volume_client.volumes.extend.side_effect = None
        self.instance.reset_mock()

    def test_resize_volume_verify_extend_no_volume(self):
        self.instance.volume_client.volumes.get = Mock(return_value=None)
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
        detach_count = self.instance.volume_client.volumes.detach.call_count
        self.assertEqual(1, detach_count)
        extend_count = self.instance.volume_client.volumes.extend.call_count
        self.assertEqual(1, extend_count)
        attach_count = self.instance.volume_client.volumes.attach.call_count
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

    def stub_inst_service_status(self, status_id, statuses):
        answers = []
        for i, status in enumerate(statuses):
            inst_svc_status = InstanceServiceStatus(status,
                                                    id="%s-%s" % (status_id,
                                                                  i))
            when(inst_svc_status).save().thenReturn(None)
            answers.append(inst_svc_status)

        when(trove.db.models.DatabaseModelBase).find_by(
            instance_id=any()).thenReturn(*answers)

    def _stub_volume_client(self):
        self.instance_task._volume_client = mock(cinderclient.Client)
        stub_volume_mgr = mock(cinderclient.volumes.VolumeManager)
        self.instance_task.volume_client.volumes = stub_volume_mgr
        stub_volume = cinderclient.volumes.Volume(stub_volume_mgr,
                                                  {'status': 'available'},
                                                  True)
        when(stub_volume_mgr).extend(VOLUME_ID, 2).thenReturn(None)
        stub_new_volume = cinderclient.volumes.Volume(
            stub_volume_mgr, {'status': 'available', 'size': 2}, True)
        when(stub_volume_mgr).get(any()).thenReturn(
            stub_volume).thenReturn(stub_new_volume)
        when(stub_volume_mgr).attach(any(), VOLUME_ID).thenReturn(None)

    def setUp(self):
        super(BuiltInstanceTasksTest, self).setUp()
        self.new_flavor = {'id': 8, 'ram': 768, 'name': 'bigger_flavor'}
        stub_nova_server = mock(novaclient.v1_1.servers.Server)
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
        when(datastore_models.DatastoreVersion).load_by_uuid(any()).thenReturn(
            datastore_models.DatastoreVersion(db_instance))
        when(datastore_models.Datastore).load('id-1').thenReturn(
            datastore_models.Datastore(db_instance))

        self.instance_task = taskmanager_models.BuiltInstanceTasks(
            trove.common.context.TroveContext(),
            db_instance,
            stub_nova_server,
            InstanceServiceStatus(ServiceStatuses.RUNNING,
                                  id='inst-stat-id-0'))

        self.instance_task._guest = mock(trove.guestagent.api.API)
        self.instance_task._nova_client = mock(novaclient.v1_1.Client)
        self.stub_server_mgr = mock(novaclient.v1_1.servers.ServerManager)
        self.stub_running_server = mock(novaclient.v1_1.servers.Server)
        self.stub_running_server.status = 'ACTIVE'
        self.stub_running_server.flavor = {'id': 6, 'ram': 512}
        self.stub_verifying_server = mock(novaclient.v1_1.servers.Server)
        self.stub_verifying_server.status = 'VERIFY_RESIZE'
        self.stub_verifying_server.flavor = {'id': 8, 'ram': 768}
        when(self.stub_server_mgr).get(any()).thenReturn(
            self.stub_verifying_server)
        self.instance_task._nova_client.servers = self.stub_server_mgr
        stub_flavor_manager = mock(novaclient.v1_1.flavors.FlavorManager)
        self.instance_task._nova_client.flavors = stub_flavor_manager

        nova_flavor = novaclient.v1_1.flavors.Flavor(stub_flavor_manager,
                                                     self.new_flavor,
                                                     True)
        when(stub_flavor_manager).get(any()).thenReturn(nova_flavor)

        self.stub_inst_service_status('inst_stat-id',
                                      [ServiceStatuses.SHUTDOWN,
                                       ServiceStatuses.RUNNING,
                                       ServiceStatuses.RUNNING])

        when(template).SingleInstanceConfigTemplate(
            any(), any(), any()).thenReturn(
                mock(template.SingleInstanceConfigTemplate))

        when(trove.db.models.DatabaseModelBase).find_by(
            id=any(), deleted=False).thenReturn(db_instance)
        when(db_instance).save().thenReturn(None)

        when(trove.backup.models.Backup).running(any()).thenReturn(None)

        if 'volume' in self._testMethodName:
            self._stub_volume_client()

    def tearDown(self):
        super(BuiltInstanceTasksTest, self).tearDown()
        unstub()

    def test_resize_flavor(self):
        orig_server = self.instance_task.server
        self.instance_task.resize_flavor({'id': 1, 'ram': 512},
                                         self.new_flavor)
        # verify
        self.assertIsNot(self.instance_task.server, orig_server)
        verify(self.instance_task._guest).stop_db(do_not_start_on_reboot=True)
        verify(orig_server).resize(self.new_flavor['id'])
        self.assertThat(self.db_instance.task_status, Is(InstanceTasks.NONE))
        verify(self.stub_server_mgr, times=1).get(any())
        self.assertThat(self.db_instance.flavor_id, Is(self.new_flavor['id']))

    def test_resize_flavor_resize_failure(self):
        orig_server = self.instance_task.server
        self.stub_verifying_server.status = 'ERROR'
        when(self.instance_task._nova_client.servers).get(any()).thenReturn(
            self.stub_verifying_server)
        # execute
        self.assertRaises(TroveError, self.instance_task.resize_flavor,
                          {'id': 1, 'ram': 512}, self.new_flavor)
        # verify
        verify(self.stub_server_mgr, times=1).get(any())
        self.assertIs(self.instance_task.server, self.stub_verifying_server)
        verify(self.instance_task._guest).stop_db(do_not_start_on_reboot=True)
        verify(orig_server).resize(self.new_flavor['id'])
        self.assertThat(self.db_instance.task_status, Is(InstanceTasks.NONE))
        self.assertThat(self.db_instance.flavor_id, Is('6'))


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
        self.backup.state = backup_models.BackupState.NEW
        self.container_content = (None,
                                  [{'name': 'first'},
                                   {'name': 'second'},
                                   {'name': 'third'}])
        when(backup_models.Backup).delete(any()).thenReturn(None)
        when(backup_models.Backup).get_by_id(
            any(), self.backup.id).thenReturn(self.backup)
        when(backup_models.DBBackup).save(any()).thenReturn(self.backup)
        when(self.backup).delete(any()).thenReturn(None)
        self.swift_client = mock()
        when(remote).create_swift_client(
            any()).thenReturn(self.swift_client)
        when(self.swift_client).head_container(
            any()).thenRaise(ClientException("foo"))
        when(self.swift_client).head_object(
            any(), any()).thenRaise(ClientException("foo"))
        when(self.swift_client).get_container(any()).thenReturn(
            self.container_content)
        when(self.swift_client).delete_object(any(), any()).thenReturn(None)
        when(self.swift_client).delete_container(any()).thenReturn(None)

    def tearDown(self):
        super(BackupTasksTest, self).tearDown()
        unstub()

    def test_delete_backup_nolocation(self):
        self.backup.location = ''
        taskmanager_models.BackupTasks.delete_backup('dummy context',
                                                     self.backup.id)
        verify(self.backup).delete()

    def test_delete_backup_fail_delete_manifest(self):
        filename = self.backup.location[self.backup.location.rfind("/") + 1:]
        when(self.swift_client).delete_object(
            any(),
            filename).thenRaise(ClientException("foo"))
        when(self.swift_client).head_object(any(), any()).thenReturn({})
        self.assertRaises(
            TroveError,
            taskmanager_models.BackupTasks.delete_backup,
            'dummy context', self.backup.id)
        verify(backup_models.Backup, never).delete(self.backup.id)
        self.assertEqual(
            backup_models.BackupState.DELETE_FAILED,
            self.backup.state,
            "backup should be in DELETE_FAILED status")

    def test_delete_backup_fail_delete_segment(self):
        when(self.swift_client).delete_object(
            any(),
            'second').thenRaise(ClientException("foo"))
        self.assertRaises(
            TroveError,
            taskmanager_models.BackupTasks.delete_backup,
            'dummy context', self.backup.id)
        verify(backup_models.Backup, never).delete(self.backup.id)
        self.assertEqual(
            backup_models.BackupState.DELETE_FAILED,
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
