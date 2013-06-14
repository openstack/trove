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
#    under the License

import trove.common.remote as remote
import testtools
import trove.taskmanager.models as taskmanager_models
import trove.backup.models as backup_models
from mockito import mock, when, unstub, any, verify, never
from swiftclient.client import ClientException


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
        self.backup.state = backup_models.BackupState.NEW
        self.container_content = (None,
                                  [{'name': 'first'},
                                   {'name': 'second'},
                                   {'name': 'third'}])
        when(backup_models.Backup).delete(any()).thenReturn(None)
        when(backup_models.Backup).get_by_id(
            any(), self.backup.id).thenReturn(self.backup)
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
        when(self.swift_client).head_object(any(), any()).thenReturn(None)
        taskmanager_models.BackupTasks.delete_backup('dummy context',
                                                     self.backup.id)
        verify(backup_models.Backup, never).delete(self.backup.id)
        self.assertEqual(backup_models.BackupState.FAILED, self.backup.state,
                         "backup should be in FAILED status")

    def test_delete_backup_fail_delete_container(self):
        when(self.swift_client).delete_container(
            any()).thenRaise(ClientException("foo"))
        when(self.swift_client).head_container(any()).thenReturn(None)
        taskmanager_models.BackupTasks.delete_backup('dummy context',
                                                     self.backup.id)
        verify(backup_models.Backup, never).delete(self.backup.id)
        self.assertEqual(backup_models.BackupState.FAILED, self.backup.state,
                         "backup should be in FAILED status")

    def test_delete_backup_fail_delete_segment(self):
        when(self.swift_client).delete_object(
            any(),
            'second').thenRaise(ClientException("foo"))
        when(self.swift_client).delete_container(
            any()).thenRaise(ClientException("foo"))
        when(self.swift_client).head_container(any()).thenReturn(None)
        taskmanager_models.BackupTasks.delete_backup('dummy context',
                                                     self.backup.id)
        verify(backup_models.Backup, never).delete(self.backup.id)
        self.assertEqual(backup_models.BackupState.FAILED, self.backup.state,
                         "backup should be in FAILED status")
