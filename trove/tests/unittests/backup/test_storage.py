# Copyright 2013 Rackspace Development Company, L.P.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib

from mock import Mock, MagicMock, patch

from trove.common.context import TroveContext
from trove.guestagent.strategies.storage import swift
from trove.guestagent.strategies.storage.swift import StreamReader
from trove.guestagent.strategies.storage.swift \
    import SwiftDownloadIntegrityError
from trove.guestagent.strategies.storage.swift import SwiftStorage
from trove.tests.fakes.swift import FakeSwiftConnection
from trove.tests.unittests.backup.test_backupagent \
    import MockBackup as MockBackupRunner
from trove.tests.unittests import trove_testtools


class SwiftStorageSaveChecksumTests(trove_testtools.TestCase):
    """SwiftStorage.save is used to save a backup to Swift."""

    def setUp(self):
        super(SwiftStorageSaveChecksumTests, self).setUp()

    def tearDown(self):
        super(SwiftStorageSaveChecksumTests, self).tearDown()

    def test_swift_checksum_save(self):
        """This tests that SwiftStorage.save returns the swift checksum."""
        context = TroveContext()
        backup_id = '123'
        user = 'user'
        password = 'password'

        swift_client = FakeSwiftConnection()
        with patch.object(swift, 'create_swift_client',
                          return_value=swift_client):
            storage_strategy = SwiftStorage(context)

            with MockBackupRunner(filename=backup_id,
                                  user=user,
                                  password=password) as runner:
                (success,
                 note,
                 checksum,
                 location) = storage_strategy.save(runner.manifest, runner)

        self.assertTrue(success, "The backup should have been successful.")
        self.assertIsNotNone(note, "A note should have been returned.")
        self.assertEqual('http://mockswift/v1/database_backups/123.gz.enc',
                         location,
                         "Incorrect swift location was returned.")

    def test_swift_segment_checksum_etag_mismatch(self):
        """This tests that when etag doesn't match segment uploaded checksum
            False is returned and None for checksum and location
        """
        context = TroveContext()
        # this backup_id will trigger fake swift client with calculate_etag
        # enabled to spit out a bad etag when a segment object is uploaded
        backup_id = 'bad_segment_etag_123'
        user = 'user'
        password = 'password'

        swift_client = FakeSwiftConnection()
        with patch.object(swift, 'create_swift_client',
                          return_value=swift_client):
            storage_strategy = SwiftStorage(context)

            with MockBackupRunner(filename=backup_id,
                                  user=user,
                                  password=password) as runner:
                (success,
                 note,
                 checksum,
                 location) = storage_strategy.save(runner.manifest, runner)

        self.assertFalse(success, "The backup should have failed!")
        self.assertTrue(note.startswith("Error saving data to Swift!"))
        self.assertIsNone(checksum,
                          "Swift checksum should be None for failed backup.")
        self.assertEqual('http://mockswift/v1/database_backups/'
                         'bad_segment_etag_123.gz.enc',
                         location,
                         "Incorrect swift location was returned.")

    def test_swift_checksum_etag_mismatch(self):
        """This tests that when etag doesn't match swift checksum False is
            returned and None for checksum and location
        """
        context = TroveContext()
        # this backup_id will trigger fake swift client with calculate_etag
        # enabled to spit out a bad etag when a segment object is uploaded
        backup_id = 'bad_manifest_etag_123'
        user = 'user'
        password = 'password'

        swift_client = FakeSwiftConnection()
        with patch.object(swift, 'create_swift_client',
                          return_value=swift_client):
            storage_strategy = SwiftStorage(context)

            with MockBackupRunner(filename=backup_id,
                                  user=user,
                                  password=password) as runner:
                (success,
                 note,
                 checksum,
                 location) = storage_strategy.save(runner.manifest, runner)

        self.assertFalse(success, "The backup should have failed!")
        self.assertTrue(note.startswith("Error saving data to Swift!"))
        self.assertIsNone(checksum,
                          "Swift checksum should be None for failed backup.")
        self.assertEqual('http://mockswift/v1/database_backups/'
                         'bad_manifest_etag_123.gz.enc',
                         location,
                         "Incorrect swift location was returned.")


class SwiftStorageUtils(trove_testtools.TestCase):

    def setUp(self):
        super(SwiftStorageUtils, self).setUp()
        self.context = TroveContext()
        self.swift_client = FakeSwiftConnection()
        self.create_swift_client_patch = patch.object(
            swift, 'create_swift_client',
            MagicMock(return_value=self.swift_client))
        self.create_swift_client_mock = self.create_swift_client_patch.start()
        self.addCleanup(self.create_swift_client_patch.stop)
        self.swift = SwiftStorage(self.context)

    def tearDown(self):
        super(SwiftStorageUtils, self).tearDown()

    def test_explode_location(self):
        location = 'http://mockswift.com/v1/545433/backups/mybackup.tar'
        url, container, filename = self.swift._explodeLocation(location)
        self.assertEqual('http://mockswift.com/v1/545433', url)
        self.assertEqual('backups', container)
        self.assertEqual('mybackup.tar', filename)

    def test_validate_checksum_good(self):
        match = self.swift._verify_checksum('"my-good-etag"', 'my-good-etag')
        self.assertTrue(match)

    def test_verify_checksum_bad(self):
        self.assertRaises(SwiftDownloadIntegrityError,
                          self.swift._verify_checksum,
                          '"THE-GOOD-THE-BAD"',
                          'AND-THE-UGLY')


class SwiftStorageLoad(trove_testtools.TestCase):
    """SwiftStorage.load is used to return SwiftDownloadStream which is used
        to download a backup object from Swift
    """

    def setUp(self):
        super(SwiftStorageLoad, self).setUp()

    def tearDown(self):
        super(SwiftStorageLoad, self).tearDown()

    def test_run_verify_checksum(self):
        """This tests that swift download cmd runs if original backup checksum
            matches swift object etag
        """

        context = TroveContext()
        location = "/backup/location/123"
        backup_checksum = "fake-md5-sum"

        swift_client = FakeSwiftConnection()
        with patch.object(swift, 'create_swift_client',
                          return_value=swift_client):

            storage_strategy = SwiftStorage(context)
            download_stream = storage_strategy.load(location, backup_checksum)
        self.assertIsNotNone(download_stream)

    def test_run_verify_checksum_mismatch(self):
        """This tests that SwiftDownloadIntegrityError is raised and swift
            download cmd does not run when original backup checksum
            does not match swift object etag
        """

        context = TroveContext()
        location = "/backup/location/123"
        backup_checksum = "checksum_different_then_fake_swift_etag"

        swift_client = FakeSwiftConnection()
        with patch.object(swift, 'create_swift_client',
                          return_value=swift_client):
            storage_strategy = SwiftStorage(context)

        self.assertRaises(SwiftDownloadIntegrityError,
                          storage_strategy.load,
                          location,
                          backup_checksum)


class MockBackupStream(MockBackupRunner):

    def read(self, chunk_size):
        return 'X' * chunk_size


class StreamReaderTests(trove_testtools.TestCase):

    def setUp(self):
        super(StreamReaderTests, self).setUp()
        self.runner = MockBackupStream(filename='123.xbstream.enc.gz',
                                       user='user',
                                       password='password')
        self.stream = StreamReader(self.runner,
                                   self.runner.manifest,
                                   max_file_size=100)

    def test_base_filename(self):
        self.assertEqual('123', self.stream.base_filename)

    def test_base_filename_no_extension(self):
        stream_reader = StreamReader(self.runner, 'foo')
        self.assertEqual('foo', stream_reader.base_filename)

    def test_prefix(self):
        self.assertEqual('database_backups/123_', self.stream.prefix)

    def test_segment(self):
        self.assertEqual('123_00000000', self.stream.segment)

    def test_end_of_file(self):
        self.assertFalse(self.stream.end_of_file)

    def test_end_of_segment(self):
        self.assertFalse(self.stream.end_of_segment)

    def test_segment_almost_complete(self):
        self.stream.segment_length = 98
        results = self.stream.read(2)
        self.assertEqual('XX', results)
        self.assertEqual('123_00000000', self.stream.segment,
                         "The Segment should still be the same")
        self.assertEqual(100, self.stream.segment_length)
        checksum = hashlib.md5('XX')
        checksum = checksum.hexdigest()
        segment_checksum = self.stream.segment_checksum.hexdigest()
        self.assertEqual(checksum, segment_checksum,
                         "Segment checksum did not match")

    def test_segment_complete(self):
        self.stream.segment_length = 99
        results = self.stream.read(2)
        self.assertEqual('', results, "Results should be empty.")
        self.assertEqual('123_00000001', self.stream.segment)

    def test_stream_complete(self):
        results = self.stream.read(0)
        self.assertEqual('', results, "Results should be empty.")
        self.assertTrue(self.stream.end_of_file)


class SwiftMetadataTests(trove_testtools.TestCase):

    def setUp(self):
        super(SwiftMetadataTests, self).setUp()
        self.swift_client = FakeSwiftConnection()
        self.context = TroveContext()
        self.create_swift_client_patch = patch.object(
            swift, 'create_swift_client',
            MagicMock(return_value=self.swift_client))
        self.create_swift_client_mock = self.create_swift_client_patch.start()
        self.addCleanup(self.create_swift_client_patch.stop)
        self.swift = SwiftStorage(self.context)

    def tearDown(self):
        super(SwiftMetadataTests, self).tearDown()

    def test__get_attr(self):
        normal_header = self.swift._get_attr('content-type')
        self.assertEqual('content_type', normal_header)
        meta_header = self.swift._get_attr('x-object-meta-foo')
        self.assertEqual('foo', meta_header)
        meta_header_two = self.swift._get_attr('x-object-meta-foo-bar')
        self.assertEqual('foo_bar', meta_header_two)

    def test__set_attr(self):
        meta_header = self.swift._set_attr('foo')
        self.assertEqual('X-Object-Meta-foo', meta_header)
        meta_header_two = self.swift._set_attr('foo_bar')
        self.assertEqual('X-Object-Meta-foo-bar', meta_header_two)

    def test_load_metadata(self):
        location = 'http://mockswift.com/v1/545433/backups/mybackup.tar'
        headers = {
            'etag': '"fake-md5-sum"',
            'x-object-meta-lsn': '1234567'
        }
        with patch.object(self.swift_client, 'head_object',
                          return_value=headers):
            metadata = self.swift.load_metadata(location, 'fake-md5-sum')
        self.assertEqual({'lsn': '1234567'}, metadata)

    def test_save_metadata(self):
        location = 'http://mockswift.com/v1/545433/backups/mybackup.tar'
        metadata = {'lsn': '1234567'}
        self.swift_client.post_object = Mock()

        self.swift.save_metadata(location, metadata=metadata)

        headers = {
            'X-Object-Meta-lsn': '1234567',
            'X-Object-Manifest': None
        }
        self.swift_client.post_object.assert_called_with(
            'backups', 'mybackup.tar', headers=headers)
