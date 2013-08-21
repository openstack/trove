#    Copyright 2012 OpenStack LLC
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

import trove.common.remote as remote
import testtools
import trove.taskmanager.models as taskmanager_models
import trove.backup.models as backup_models
from trove.common.exception import TroveError
from mockito import mock, when, unstub, any, verify, never
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


class fake_ServerManager:
    def create(self, name, image_id, flavor_id, files, userdata,
               security_groups, block_device_mapping):
        server = fake_Server()
        server.id = "server_id"
        server.name = name
        server.image_id = image_id
        server.flavor_id = flavor_id
        server.files = files
        server.userdata = userdata
        server.security_groups = security_groups
        server.block_device_mapping = block_device_mapping
        return server


class fake_nova_client:
    def __init__(self):
        self.servers = fake_ServerManager()


class FreshInstanceTasksTest(testtools.TestCase):
    def setUp(self):
        super(FreshInstanceTasksTest, self).setUp()
        when(taskmanager_models.FreshInstanceTasks).id().thenReturn(
            "instance_id")
        when(taskmanager_models.FreshInstanceTasks).hostname().thenReturn(
            "hostname")
        taskmanager_models.FreshInstanceTasks.nova_client = fake_nova_client()
        taskmanager_models.CONF = mock()
        when(taskmanager_models.CONF).get(any()).thenReturn('')
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
        unstub()

    def test_create_instance_userdata(self):
        cloudinit_location = os.path.dirname(self.cloudinit)
        service_type = os.path.splitext(os.path.basename(self.cloudinit))[0]
        when(taskmanager_models.CONF).get("cloudinit_location").thenReturn(
            cloudinit_location)
        server = self.freshinstancetasks._create_server(None, None, None,
                                                        service_type, None)
        self.assertEqual(server.userdata, self.userdata)

    def test_create_instance_guestconfig(self):
        when(taskmanager_models.CONF).get("guest_config").thenReturn(
            self.guestconfig)
        server = self.freshinstancetasks._create_server(None, None, None,
                                                        "test", None)
        self.assertTrue('/etc/trove-guestagent.conf' in server.files)
        self.assertEqual(server.files['/etc/trove-guestagent.conf'],
                         self.guestconfig_content)


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
