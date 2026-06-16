# Copyright 2026 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from oslo_config import cfg
from unittest import mock

from backup.drivers import base as drivers_base
import backup.main
from backup.storage import swift
from trove.tests.unittests import trove_testtools


class MockStream(drivers_base.BaseRunner):

    def __init__(self):
        self.datadir = '/var/lib/data'
        super(MockStream, self).__init__(filename='backup')

    def read(self, chunk_size):
        return None


class TestSwift(trove_testtools.TestCase):

    def setUp(self):
        self.token = '12345678910'
        self.project_id = self.random_uuid()
        self.auth_url = 'https://keystone.com/v3'
        self.object_url = f"https://object.cloud.com/AUTH_{self.project_id}"
        self.region_name = "RegionOne"
        super(TestSwift, self).setUp()
        # Some cli options may conflict with configuration options
        cfg.CONF.unregister_opts(backup.main.cli_opts)
        cfg.CONF.register_cli_opts(backup.main.cli_opts)
        self.patch_conf_property('swift_url', self.object_url)
        self.patch_conf_property('swift_api_insecure', True)
        self.patch_conf_property('os_token', self.token)

    @mock.patch('backup.storage.swift.swiftclient.Connection')
    def test_passing_swift_url(self, mock_connection):
        # Setup mock connection
        mock_client = mock.MagicMock()
        mock_client.url = self.object_url
        mock_connection.return_value = mock_client

        # Configure mock responses
        mock_client.put_container.return_value = None
        # Force checksum verification failure.
        mock_client.put_object.return_value = 'different_etag'

        stream = MockStream()
        swift_container_name = 'backup_20260605'

        storage = swift.SwiftStorage()
        # The upload of the segment will fail due to etag and MD5 hash mismatch
        with self.assertRaisesRegex(
                Exception,
                r'Failed to upload data segment to swift. '
                r'ETAG: different_etag .+\.$'):
            storage.save(stream, container=swift_container_name)

        # Verify the connection was created with correct parameters
        mock_connection.assert_called_once_with(
            preauthurl=self.object_url,
            preauthtoken=self.token,
            insecure=True
        )

        # Verify container creation was attempted
        mock_client.put_container.assert_called_with(swift_container_name)

        # Verify segment upload was attempted
        mock_client.put_object.assert_called()

    @mock.patch('backup.storage.swift._get_service_client')
    def test_legacy_client_support(self, mock_get_service_client):
        """Test backward compatibility with old guest agents that use
        token rescope instead of pre-authenticated Swift URLs.
        """
        # Remove swift_url to trigger legacy path
        self.patch_conf_property('swift_url', None)
        self.patch_conf_property('swift_api_insecure', False)
        self.patch_conf_property('os_auth_url', self.auth_url)
        self.patch_conf_property('os_token', self.token)
        self.patch_conf_property('os_tenant_id', self.project_id)
        self.patch_conf_property('os_region_name', self.region_name)

        # Setup mock legacy client
        mock_legacy_client = mock.MagicMock()
        mock_legacy_client.url = self.object_url
        mock_legacy_client.put_object.return_value = 'different_etag'
        mock_get_service_client.return_value = mock_legacy_client

        stream = MockStream()
        swift_container_name = 'backup_20260605'

        storage = swift.SwiftStorage()

        # Verify legacy client was created with correct parameters
        mock_get_service_client.assert_called_once_with(
            self.auth_url,
            self.token,
            self.project_id,
            region_name=self.region_name,
            insecure=False
        )

        # Test that the legacy client works for operations
        with self.assertRaisesRegex(
            Exception,
            (r'Failed to upload data segment to swift. '
             r'ETAG: different_etag .+\.$')
        ):
            storage.save(stream, container=swift_container_name)

        # Verify legacy client methods were called
        mock_legacy_client.put_container.assert_called_with(
            swift_container_name)
        mock_legacy_client.put_object.assert_called()
