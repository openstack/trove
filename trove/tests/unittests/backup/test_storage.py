#Copyright 2013 Rackspace Development Company, L.P.

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

import testtools
from mockito import when, verify, unstub, mock, any, contains
from trove.common.context import TroveContext

from trove.tests.fakes.swift import fake_create_swift_client
from trove.tests.unittests.backup.test_backupagent \
    import MockBackup as MockBackupRunner
from trove.guestagent.strategies.storage.swift \
    import SwiftDownloadIntegrityError
from trove.guestagent.strategies.storage import swift
from trove.guestagent.strategies.storage.swift import SwiftStorage


class MockProcess(object):
    """Fake swift download process"""

    def __init__(self):
        self.pid = 1
        self.stdout = "Mock Process stdout."

    def terminate(self):
        pass


class SwiftStorageSaveChecksumTests(testtools.TestCase):
    """SwiftStorage.save is used to save a backup to Swift"""

    def setUp(self):
        super(SwiftStorageSaveChecksumTests, self).setUp()

    def tearDown(self):
        super(SwiftStorageSaveChecksumTests, self).tearDown()
        unstub()

    def test_swift_checksum_save(self):
        """This tests that SwiftStorage.save returns the swift checksum"""
        context = TroveContext()
        backup_id = '123'
        user = 'user'
        password = 'password'
        backup_container = 'database_backups'

        swift_client = fake_create_swift_client(calculate_etag=True)
        when(swift).create_swift_client(context).thenReturn(swift_client)
        storage_strategy = SwiftStorage(context)

        with MockBackupRunner(filename=backup_id,
                              user=user,
                              password=password) as runner:
            (success,
             note,
             checksum,
             location) = storage_strategy.save(backup_container, runner)

        self.assertEqual(success, True,
                         "The backup should have been successful.")
        self.assertIsNotNone(note, "A note should have been returned.")
        self.assertEqual(location, 'http://mockswift/v1/database_backups/123',
                         "Incorrect swift location was returned.")

    def test_swift_segment_checksum_etag_mismatch(self):
        """This tests that when etag doesn't match segment uploaded checksum
        False is returned and None for checksum and location"""
        context = TroveContext()
        # this backup_id will trigger fake swift client with calculate_etag
        # enabled to spit out a bad etag when a segment object is uploaded
        backup_id = 'bad_segment_etag_123'
        user = 'user'
        password = 'password'
        backup_container = 'database_backups'

        swift_client = fake_create_swift_client(calculate_etag=True)
        when(swift).create_swift_client(context).thenReturn(swift_client)
        storage_strategy = SwiftStorage(context)

        with MockBackupRunner(filename=backup_id,
                              user=user,
                              password=password) as runner:
            (success,
             note,
             checksum,
             location) = storage_strategy.save(backup_container, runner)

        self.assertEqual(success, False,
                         "The backup should have failed!")
        self.assertTrue(note.startswith("Error saving data to Swift!"))
        self.assertIsNone(checksum,
                          "Swift checksum should be None for failed backup.")
        self.assertIsNone(location,
                          "Swift location should be None for failed backup.")

    def test_swift_checksum_etag_mismatch(self):
        """This tests that when etag doesn't match swift checksum False is
        returned and None for checksum and location"""
        context = TroveContext()
        # this backup_id will trigger fake swift client with calculate_etag
        # enabled to spit out a bad etag when a segment object is uploaded
        backup_id = 'bad_manifest_etag_123'
        user = 'user'
        password = 'password'
        backup_container = 'database_backups'

        swift_client = fake_create_swift_client(calculate_etag=True)
        when(swift).create_swift_client(context).thenReturn(swift_client)
        storage_strategy = SwiftStorage(context)

        with MockBackupRunner(filename=backup_id,
                              user=user,
                              password=password) as runner:
            (success,
             note,
             checksum,
             location) = storage_strategy.save(backup_container, runner)

        self.assertEqual(success, False,
                         "The backup should have failed!")
        self.assertTrue(note.startswith("Error saving data to Swift!"))
        self.assertIsNone(checksum,
                          "Swift checksum should be None for failed backup.")
        self.assertIsNone(location,
                          "Swift location should be None for failed backup.")


class SwiftStorageLoad(testtools.TestCase):
    """SwiftStorage.load is used to return SwiftDownloadStream which is used
    to download a backup object from Swift"""

    def setUp(self):
        super(SwiftStorageLoad, self).setUp()

    def tearDown(self):
        super(SwiftStorageLoad, self).tearDown()
        unstub()

    def test_run_verify_checksum(self):
        """This tests that swift download cmd runs if original backup checksum
        matches swift object etag"""

        context = TroveContext()
        location = "/backup/location/123"
        is_zipped = False
        backup_checksum = "fake-md5-sum"

        swift_client = fake_create_swift_client()
        when(swift).create_swift_client(context).thenReturn(swift_client)
        download_process = MockProcess()
        subprocess = mock(swift.subprocess)
        when(subprocess).Popen(any(), any(),
                               any(), any()).thenReturn(download_process)
        when(swift.utils).raise_if_process_errored().thenReturn(None)

        storage_strategy = SwiftStorage(context)
        download_stream = storage_strategy.load(context,
                                                location,
                                                is_zipped,
                                                backup_checksum)

        self.assertEqual(download_stream.container, "location")
        self.assertEqual(download_stream.filename, "123")

        with download_stream as stream:
            print "Testing SwiftDownloadStream context manager: %s" % stream

        self.assertIsNotNone(download_stream.process,
                             "SwiftDownloadStream process/cmd is supposed "
                             "to run.")
        self.assertIsNotNone(download_stream.pid,
                             "SwiftDownloadStream process/cmd is supposed "
                             "to run.")

    def test_run_verify_checksum_mismatch(self):
        """This tests that SwiftDownloadIntegrityError is raised and swift
        download cmd does not run when original backup checksum does not match
        swift object etag"""

        context = TroveContext()
        location = "/backup/location/123"
        is_zipped = False
        backup_checksum = "checksum_different_then_fake_swift_etag"

        swift_client = fake_create_swift_client()
        when(swift).create_swift_client(context).thenReturn(swift_client)

        storage_strategy = SwiftStorage(context)
        download_stream = storage_strategy.load(context,
                                                location,
                                                is_zipped,
                                                backup_checksum)

        self.assertEqual(download_stream.container, "location")
        self.assertEqual(download_stream.filename, "123")

        self.assertRaises(SwiftDownloadIntegrityError,
                          download_stream.__enter__)

        self.assertEqual(download_stream.process, None,
                         "SwiftDownloadStream process/cmd was not supposed"
                         "to run.")
