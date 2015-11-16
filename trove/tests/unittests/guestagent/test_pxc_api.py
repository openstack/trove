# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
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

from eventlet import Timeout
import mock

import trove.common.context as context
from trove.common import exception
from trove.common.rpc.version import RPC_API_VERSION
from trove.common.strategies.cluster.experimental.pxc.guestagent import (
    PXCGuestAgentAPI)
from trove import rpc
from trove.tests.unittests import trove_testtools


def _mock_call(cmd, timeout, version=None, user=None,
               public_keys=None, members=None):
    # To check get_public_keys, authorize_public_keys,
    # install_cluster, cluster_complete in cmd.
    if cmd in ('get_public_keys', 'authorize_public_keys',
               'install_cluster', 'cluster_complete'):
        return True
    else:
        raise BaseException("Test Failed")


class ApiTest(trove_testtools.TestCase):
    @mock.patch.object(rpc, 'get_client')
    def setUp(self, *args):
        super(ApiTest, self).setUp()
        self.context = context.TroveContext()
        self.guest = PXCGuestAgentAPI(self.context, 0)
        self.guest._call = _mock_call
        self.api = PXCGuestAgentAPI(self.context, "instance-id-x23d2d")
        self._mock_rpc_client()

    def test_get_routing_key(self):
        self.assertEqual('guestagent.instance-id-x23d2d',
                         self.api._get_routing_key())

    @mock.patch('trove.guestagent.api.LOG')
    def test_api_cast_exception(self, mock_logging):
        self.call_context.cast.side_effect = IOError('host down')
        self.assertRaises(exception.GuestError, self.api.create_user,
                          'test_user')

    @mock.patch('trove.guestagent.api.LOG')
    def test_api_call_exception(self, mock_logging):
        self.call_context.call.side_effect = IOError('host_down')
        self.assertRaises(exception.GuestError, self.api.list_users)

    def test_api_call_timeout(self):
        self.call_context.call.side_effect = Timeout()
        self.assertRaises(exception.GuestTimeout, self.api.restart)

    def _verify_rpc_prepare_before_call(self):
        self.api.client.prepare.assert_called_once_with(
            version=RPC_API_VERSION, timeout=mock.ANY)

    def _verify_rpc_prepare_before_cast(self):
        self.api.client.prepare.assert_called_once_with(
            version=RPC_API_VERSION)

    def _verify_cast(self, *args, **kwargs):
        self.call_context.cast.assert_called_once_with(self.context, *args,
                                                       **kwargs)

    def _verify_call(self, *args, **kwargs):
        self.call_context.call.assert_called_once_with(self.context, *args,
                                                       **kwargs)

    def _mock_rpc_client(self):
        self.call_context = mock.Mock()
        self.api.client.prepare = mock.Mock(return_value=self.call_context)
        self.call_context.call = mock.Mock()
        self.call_context.cast = mock.Mock()

    def test_install_cluster(self):
        exp_resp = None
        self.call_context.call.return_value = exp_resp

        resp = self.api.install_cluster(
            replication_user="repuser",
            cluster_configuration="cluster-configuration",
            bootstrap=False)

        self._verify_rpc_prepare_before_call()
        self._verify_call('install_cluster', replication_user="repuser",
                          cluster_configuration="cluster-configuration",
                          bootstrap=False)
        self.assertEqual(exp_resp, resp)

    def test_reset_admin_password(self):
        exp_resp = None
        self.call_context.call.return_value = exp_resp

        resp = self.api.reset_admin_password(
            admin_password="admin_password")

        self._verify_rpc_prepare_before_call()
        self._verify_call('reset_admin_password',
                          admin_password="admin_password")
        self.assertEqual(exp_resp, resp)

    def test_cluster_complete(self):
        exp_resp = None
        self.call_context.call.return_value = exp_resp

        resp = self.api.cluster_complete()

        self._verify_rpc_prepare_before_call()
        self._verify_call('cluster_complete')
        self.assertEqual(exp_resp, resp)

    def test_get_cluster_context(self):
        exp_resp = None
        self.call_context.call.return_value = exp_resp

        resp = self.api.get_cluster_context()

        self._verify_rpc_prepare_before_call()
        self._verify_call('get_cluster_context')
        self.assertEqual(exp_resp, resp)

    def test_write_cluster_configuration_overrides(self):
        exp_resp = None
        self.call_context.call.return_value = exp_resp

        resp = self.api.write_cluster_configuration_overrides(
            cluster_configuration="cluster-configuration")

        self._verify_rpc_prepare_before_call()
        self._verify_call('write_cluster_configuration_overrides',
                          cluster_configuration="cluster-configuration",)
        self.assertEqual(exp_resp, resp)
