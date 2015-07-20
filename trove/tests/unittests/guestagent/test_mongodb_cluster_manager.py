# Copyright 2014 eBay Software Foundation
# All Rights Reserved.
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

import mock
from oslo_utils import netutils
import pymongo

import trove.common.context as context
import trove.common.instance as ds_instance
import trove.common.utils as utils
from trove.guestagent.common import operating_system
import trove.guestagent.datastore.experimental.mongodb.manager as manager
import trove.guestagent.datastore.experimental.mongodb.service as service
import trove.guestagent.datastore.experimental.mongodb.system as system
import trove.guestagent.volume as volume
import trove.tests.unittests.trove_testtools as trove_testtools


class GuestAgentMongoDBClusterManagerTest(trove_testtools.TestCase):

    @mock.patch.object(service.MongoDBApp, '_init_overrides_dir')
    def setUp(self, _):
        super(GuestAgentMongoDBClusterManagerTest, self).setUp()
        self.context = context.TroveContext()
        self.manager = manager.Manager()
        self.manager.app.configuration_manager = mock.MagicMock()
        self.manager.app.status = mock.MagicMock()
        self.conf_mgr = self.manager.app.configuration_manager

        self.pymongo_patch = mock.patch.object(
            pymongo, 'MongoClient'
        )
        self.addCleanup(self.pymongo_patch.stop)
        self.pymongo_patch.start()

    def tearDown(self):
        super(GuestAgentMongoDBClusterManagerTest, self).tearDown()

    @mock.patch.object(service.MongoDBApp, 'add_members',
                       side_effect=RuntimeError("Boom!"))
    def test_add_members_failure(self, mock_add_members):
        members = ["test1", "test2"]
        self.assertRaises(RuntimeError, self.manager.add_members,
                          self.context, members)
        self.manager.app.status.set_status.assert_called_with(
            ds_instance.ServiceStatuses.FAILED)

    @mock.patch.object(utils, 'poll_until')
    @mock.patch.object(service.MongoDBAdmin, 'rs_initiate')
    @mock.patch.object(service.MongoDBAdmin, 'rs_add_members')
    def test_add_member(self, mock_add, mock_initiate, mock_poll):
        members = ["test1", "test2"]
        self.manager.add_members(self.context, members)
        mock_initiate.assert_any_call()
        mock_add.assert_any_call(["test1", "test2"])

    @mock.patch.object(service.MongoDBApp, 'restart')
    @mock.patch.object(service.MongoDBApp, 'create_admin_user')
    @mock.patch.object(utils, 'generate_random_password', return_value='pwd')
    def test_prep_primary(self, mock_pwd, mock_user, mock_restart):
        self.manager.prep_primary(self.context)
        mock_user.assert_called_with('pwd')
        mock_restart.assert_called_with()

    @mock.patch.object(service.MongoDBApp, 'add_shard',
                       side_effect=RuntimeError("Boom!"))
    def test_add_shard_failure(self, mock_add_shard):
        self.assertRaises(RuntimeError, self.manager.add_shard,
                          self.context, "rs", "rs_member")
        self.manager.app.status.set_status.assert_called_with(
            ds_instance.ServiceStatuses.FAILED)

    @mock.patch.object(service.MongoDBAdmin, 'add_shard')
    def test_add_shard(self, mock_add_shard):
        self.manager.add_shard(self.context, "rs", "rs_member")
        mock_add_shard.assert_called_with("rs/rs_member:27017")

    @mock.patch.object(service.MongoDBApp, 'add_config_servers',
                       side_effect=RuntimeError("Boom!"))
    def test_add_config_server_failure(self, mock_add_config):
        self.assertRaises(RuntimeError, self.manager.add_config_servers,
                          self.context,
                          ["cfg_server1", "cfg_server2"])
        self.manager.app.status.set_status.assert_called_with(
            ds_instance.ServiceStatuses.FAILED)

    @mock.patch.object(service.MongoDBApp, 'start_db')
    def test_add_config_servers(self, mock_start_db):
        self.manager.add_config_servers(self.context,
                                        ["cfg_server1",
                                         "cfg_server2"])
        self.conf_mgr.apply_system_override.assert_called_once_with(
            {'sharding.configDB': "cfg_server1:27019,cfg_server2:27019"},
            'clustering')
        mock_start_db.assert_called_with(True)

    @mock.patch.object(service.MongoDBApp, '_configure_as_query_router')
    @mock.patch.object(service.MongoDBApp, '_configure_cluster_security')
    def test_prepare_mongos(self, mock_secure, mock_config):
        self._prepare_method("test-id-1", "query_router", None)
        mock_config.assert_called_once_with()
        mock_secure.assert_called_once_with(None)
        self.manager.app.status.set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @mock.patch.object(service.MongoDBApp, '_configure_as_config_server')
    @mock.patch.object(service.MongoDBApp, '_configure_cluster_security')
    def test_prepare_config_server(self, mock_secure, mock_config):
        self._prepare_method("test-id-2", "config_server", None)
        mock_config.assert_called_once_with()
        mock_secure.assert_called_once_with(None)
        self.manager.app.status.set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @mock.patch.object(service.MongoDBApp, '_configure_as_cluster_member')
    @mock.patch.object(service.MongoDBApp, '_configure_cluster_security')
    def test_prepare_member(self, mock_secure, mock_config):
        self._prepare_method("test-id-3", "member", None)
        mock_config.assert_called_once_with('rs1')
        mock_secure.assert_called_once_with(None)
        self.manager.app.status.set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @mock.patch.object(operating_system, 'write_file')
    @mock.patch.object(service.MongoDBApp, '_configure_network')
    def test_configure_as_query_router(self, net_conf, os_write_file):
        self.conf_mgr.parse_configuration = mock.Mock(
            return_value={'storage.mmapv1.smallFiles': False,
                          'storage.journal.enabled': True})
        self.manager.app._configure_as_query_router()
        os_write_file.assert_called_once_with(system.MONGOS_UPSTART, mock.ANY,
                                              as_root=True)
        self.conf_mgr.save_configuration.assert_called_once_with({})
        net_conf.assert_called_once_with(service.MONGODB_PORT)
        self.conf_mgr.apply_system_override.assert_called_once_with(
            {'sharding.configDB': ''}, 'clustering')
        self.assertTrue(self.manager.app.is_query_router)

    @mock.patch.object(service.MongoDBApp, '_configure_network')
    def test_configure_as_config_server(self, net_conf):
        self.manager.app._configure_as_config_server()
        net_conf.assert_called_once_with(service.CONFIGSVR_PORT)
        self.conf_mgr.apply_system_override.assert_called_once_with(
            {'sharding.clusterRole': 'configsvr'}, 'clustering')

    @mock.patch.object(service.MongoDBApp, 'start_db')
    @mock.patch.object(service.MongoDBApp, '_configure_network')
    def test_configure_as_cluster_member(self, net_conf, start):
        self.manager.app._configure_as_cluster_member('rs1')
        net_conf.assert_called_once_with(service.MONGODB_PORT)
        self.conf_mgr.apply_system_override.assert_called_once_with(
            {'replication.replSetName': 'rs1'}, 'clustering')

    @mock.patch.object(service.MongoDBApp, 'store_key')
    @mock.patch.object(service.MongoDBApp, 'get_key_file',
                       return_value='/var/keypath')
    def test_configure_cluster_security(self, get_key_mock, store_key_mock):
        self.manager.app._configure_cluster_security('key')
        store_key_mock.assert_called_once_with('key')
        self.conf_mgr.apply_system_override.assert_called_once_with(
            {'security.clusterAuthMode': 'keyFile',
             'security.keyFile': '/var/keypath'}, 'clustering')

    @mock.patch.object(netutils, 'get_my_ipv4', return_value="10.0.0.2")
    def test_configure_network(self, ip_mock):
        self.manager.app._configure_network()
        self.conf_mgr.apply_system_override.assert_called_once_with(
            {'net.bindIp': '10.0.0.2,127.0.0.1'})
        self.manager.app.status.set_host.assert_called_once_with(
            '10.0.0.2', port=None)

        self.manager.app._configure_network(10000)
        self.conf_mgr.apply_system_override.assert_called_with(
            {'net.bindIp': '10.0.0.2,127.0.0.1',
             'net.port': 10000})
        self.manager.app.status.set_host.assert_called_with(
            '10.0.0.2', port=10000)

    @mock.patch.object(utils, 'poll_until')
    @mock.patch.object(service.MongoDBApp, 'get_key_file',
                       return_value="/test/key/file")
    @mock.patch.object(volume.VolumeDevice, 'mount_points', return_value=[])
    @mock.patch.object(volume.VolumeDevice, 'mount', return_value=None)
    @mock.patch.object(volume.VolumeDevice, 'migrate_data', return_value=None)
    @mock.patch.object(volume.VolumeDevice, 'format', return_value=None)
    @mock.patch.object(service.MongoDBApp, 'clear_storage')
    @mock.patch.object(service.MongoDBApp, 'start_db')
    @mock.patch.object(service.MongoDBApp, 'stop_db')
    @mock.patch.object(service.MongoDBApp, 'wait_for_start')
    @mock.patch.object(service.MongoDBApp, 'install_if_needed')
    @mock.patch.object(service.MongoDBAppStatus, 'begin_install')
    def _prepare_method(self, instance_id, instance_type, key, *args):
        cluster_config = {"id": instance_id,
                          "shard_id": "test_shard_id",
                          "instance_type": instance_type,
                          "replica_set_name": "rs1",
                          "key": key}

        # invocation
        self.manager.prepare(context=self.context, databases=None,
                             packages=['package'],
                             memory_mb='2048', users=None,
                             mount_point='/var/lib/mongodb',
                             overrides=None,
                             cluster_config=cluster_config)
