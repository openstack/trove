# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest
from unittest.mock import MagicMock, patch

from oslo_config import cfg
from oslo_log import log as logging

from backup.storage import swift as swift_storage

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class TestGetUserKeystoneSession(unittest.TestCase):
    def setUp(self):
        self.auth_url = 'https://keystone.example.com/v3'
        self.token = 'abc-token'

    def test_token_is_constructed_without_scope(self):
        '''Check v3.Token receives only auth_url and token'''
        with patch.object(swift_storage, 'v3') as mock_v3, \
                patch.object(swift_storage, 'session') as mock_session:
            auth = mock_v3.Token.return_value
            sess = mock_session.Session.return_value

            # call the method
            result = swift_storage._get_user_keystone_session(
                self.auth_url, self.token)

            # assertions
            mock_v3.Token.assert_called_once_with(
                auth_url=self.auth_url, token=self.token)
            mock_session.Session.assert_called_once_with(
                auth=auth, verify=False)
            self.assertIs(result, sess)

    def test_token_does_not_receive_project_scope(self):
        '''Check rescope parameters are never passed to v3.Token'''
        with patch.object(swift_storage, 'v3') as mock_v3:
            # call the method
            swift_storage._get_user_keystone_session(
                self.auth_url, self.token)

            # assertions
            _args, kwargs = mock_v3.Token.call_args
            for scope_kw in ('project_id', 'project_domain_name',
                             'project_name', 'domain_id', 'domain_name'):
                self.assertNotIn(scope_kw, kwargs)


class TestGetServiceClient(unittest.TestCase):
    def setUp(self):
        self.auth_url = 'https://keystone.example.com/v3'
        self.token = 'abc-token'

    def test_passes_region_when_provided(self):
        '''Check region_name is forwarded to swiftclient as os_options'''
        with patch.object(swift_storage, 'swiftclient') as mock_swiftclient, \
                patch.object(swift_storage,
                             '_get_user_keystone_session') as mock_get_sess:
            sess = MagicMock()
            mock_get_sess.return_value = sess

            # call the method
            swift_storage._get_service_client(
                self.auth_url, self.token, region_name='RegionTwo')

            # assertions
            mock_get_sess.assert_called_once_with(self.auth_url, self.token)
            mock_swiftclient.Connection.assert_called_once_with(
                session=sess,
                os_options={'region_name': 'RegionTwo'},
                insecure=True)

    def test_omits_os_options_when_no_region(self):
        '''Check os_options is None when region_name is not provided'''
        with patch.object(swift_storage, 'swiftclient') as mock_swiftclient, \
                patch.object(swift_storage,
                             '_get_user_keystone_session') as mock_get_sess:
            sess = MagicMock()
            mock_get_sess.return_value = sess

            # call the method
            swift_storage._get_service_client(self.auth_url, self.token)

            # assertions
            mock_swiftclient.Connection.assert_called_once_with(
                session=sess, os_options=None, insecure=True)


if __name__ == '__main__':
    unittest.main()
