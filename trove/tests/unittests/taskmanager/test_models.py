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
import testtools
from mock import Mock
from testtools.matchers import Equals
from mockito import mock, when, unstub, any, verify, never
from trove.taskmanager import models as taskmanager_models
import trove.common.remote as remote
from trove.common.instance import ServiceStatuses
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import DBInstance
from trove.instance.tasks import InstanceTasks
import trove.backup.models as backup_models
from trove.common.exception import TroveError
from swiftclient.client import ClientException
from tempfile import NamedTemporaryFile
import os


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
               security_groups, block_device_mapping, availability_zone=None):
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
        taskmanager_models.FreshInstanceTasks.nova_client = fake_nova_client()
        taskmanager_models.CONF = mock()
        when(taskmanager_models.CONF).get(any()).thenReturn('')
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
            None, None, None, None)

    def tearDown(self):
        super(FreshInstanceTasksTest, self).tearDown()
        os.remove(self.cloudinit)
        os.remove(self.guestconfig)
        InstanceServiceStatus.find_by = self.orig_ISS_find_by
        DBInstance.find_by = self.orig_DBI_find_by
        unstub()

    def test_create_instance_userdata(self):
        cloudinit_location = os.path.dirname(self.cloudinit)
        service_type = os.path.splitext(os.path.basename(self.cloudinit))[0]
        when(taskmanager_models.CONF).get("cloudinit_location").thenReturn(
            cloudinit_location)
        server = self.freshinstancetasks._create_server(
            None, None, None, service_type, None, None)
        self.assertEqual(server.userdata, self.userdata)

    def test_create_instance_guestconfig(self):
        when(taskmanager_models.CONF).get("guest_config").thenReturn(
            self.guestconfig)
        server = self.freshinstancetasks._create_server(
            None, None, None, "test", None, None)
        self.assertTrue('/etc/trove-guestagent.conf' in server.files)
        self.assertEqual(server.files['/etc/trove-guestagent.conf'],
                         self.guestconfig_content)

    def test_create_instance_with_az_kwarg(self):
        service_type = 'mysql'
        server = self.freshinstancetasks._create_server(
            None, None, None, service_type, None, availability_zone='nova')

        self.assertIsNotNone(server)

    def test_create_instance_with_az(self):
        service_type = 'mysql'
        server = self.freshinstancetasks._create_server(
            None, None, None, service_type, None, 'nova')

        self.assertIsNotNone(server)

    def test_create_instance_with_az_none(self):
        service_type = 'mysql'
        server = self.freshinstancetasks._create_server(
            None, None, None, service_type, None, None)

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
