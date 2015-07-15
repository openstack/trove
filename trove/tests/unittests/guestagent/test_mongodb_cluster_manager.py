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
import trove.guestagent.datastore.experimental.mongodb.manager as manager
import trove.guestagent.datastore.experimental.mongodb.service as service
import trove.guestagent.volume as volume
import trove.tests.unittests.trove_testtools as trove_testtools


class GuestAgentMongoDBClusterManagerTest(trove_testtools.TestCase):

    def setUp(self):
        super(GuestAgentMongoDBClusterManagerTest, self).setUp()
        self.context = context.TroveContext()
        self.manager = manager.Manager()

        self.pymongo_patch = mock.patch.object(
            pymongo, 'MongoClient'
        )
        self.addCleanup(self.pymongo_patch.stop)
        self.pymongo_patch.start()

    def tearDown(self):
        super(GuestAgentMongoDBClusterManagerTest, self).tearDown()

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(service.MongoDBApp, 'add_members',
                       side_effect=RuntimeError("Boom!"))
    def test_add_members_failure(self, mock_add_members, mock_set_status):
        members = ["test1", "test2"]
        self.assertRaises(RuntimeError, self.manager.add_members,
                          self.context, members)
        mock_set_status.assert_called_with(ds_instance.ServiceStatuses.FAILED)

    @mock.patch.object(utils, 'poll_until')
    @mock.patch.object(utils, 'generate_random_password', return_value='pwd')
    @mock.patch.object(service.MongoDBApp, 'create_admin_user')
    @mock.patch.object(service.MongoDBAdmin, 'rs_initiate')
    @mock.patch.object(service.MongoDBAdmin, 'rs_add_members')
    def test_add_member(self, mock_add, mock_initiate,
                        mock_user, mock_pwd, mock_poll):
        members = ["test1", "test2"]
        self.manager.add_members(self.context, members)
        mock_user.assert_any_call('pwd')
        mock_initiate.assert_any_call()
        mock_add.assert_any_call(["test1", "test2"])

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(service.MongoDBApp, 'add_shard',
                       side_effect=RuntimeError("Boom!"))
    def test_add_shard_failure(self, mock_add_shard, mock_set_status):
        self.assertRaises(RuntimeError, self.manager.add_shard,
                          self.context, "rs", "rs_member")
        mock_set_status.assert_called_with(ds_instance.ServiceStatuses.FAILED)

    @mock.patch.object(service.MongoDBAdmin, 'add_shard')
    def test_add_shard(self, mock_add_shard):
        self.manager.add_shard(self.context, "rs", "rs_member")
        mock_add_shard.assert_called_with("rs/rs_member:27017")

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(service.MongoDBApp, 'add_config_servers',
                       side_effect=RuntimeError("Boom!"))
    def test_add_config_server_failure(self, mock_add_config,
                                       mock_set_status):
        self.assertRaises(RuntimeError, self.manager.add_config_servers,
                          self.context,
                          ["cfg_server1", "cfg_server2"])
        mock_set_status.assert_called_with(ds_instance.ServiceStatuses.FAILED)

    @mock.patch.object(service.MongoDBApp, 'start_db_with_conf_changes')
    @mock.patch.object(service.MongoDBApp, '_add_config_parameter',
                       return_value="")
    @mock.patch.object(service.MongoDBApp, '_delete_config_parameters',
                       return_value="")
    @mock.patch.object(service.MongoDBApp, '_read_config', return_value="")
    def test_add_config_servers(self, mock_read, mock_delete,
                                mock_add, mock_start):
        self.manager.add_config_servers(self.context,
                                        ["cfg_server1",
                                         "cfg_server2"])
        mock_read.assert_called_with()
        mock_delete.assert_called_with("", ["dbpath", "nojournal",
                                            "smallfiles", "journal",
                                            "noprealloc", "configdb"])
        mock_add.assert_called_with("", "configdb",
                                    "cfg_server1:27019,cfg_server2:27019")
        mock_start.assert_called_with("")

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(service.MongoDBApp, 'write_mongos_upstart')
    @mock.patch.object(service.MongoDBApp, 'reset_configuration')
    @mock.patch.object(service.MongoDBApp, 'update_config_contents')
    @mock.patch.object(service.MongoDBApp, 'secure')
    @mock.patch.object(service.MongoDBApp, 'get_key_file',
                       return_value="/test/key/file")
    @mock.patch.object(netutils, 'get_my_ipv4', return_value="10.0.0.2")
    def test_prepare_mongos(self, mock_ip_address, mock_key_file,
                            mock_secure, mock_update, mock_reset,
                            mock_upstart, mock_set_status):

        self._prepare_method("test-id-1", "query_router", None)
        mock_update.assert_called_with(None, {'bind_ip': '10.0.0.2,127.0.0.1',
                                              # 'keyFile': '/test/key/file'})
                                              })
        self.assertTrue(self.manager.app.status.is_query_router)
        mock_set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(utils, 'poll_until')
    @mock.patch.object(service.MongoDBApp, 'start_db_with_conf_changes')
    @mock.patch.object(service.MongoDBApp, 'update_config_contents')
    @mock.patch.object(service.MongoDBApp, 'secure')
    @mock.patch.object(service.MongoDBApp, 'get_key_file',
                       return_value="/test/key/file")
    @mock.patch.object(netutils, 'get_my_ipv4', return_value="10.0.0.3")
    def test_prepare_config_server(self, mock_ip_address, mock_key_file,
                                   mock_secure, mock_update, mock_start,
                                   mock_poll, mock_set_status):
        self._prepare_method("test-id-2", "config_server", None)
        mock_update.assert_called_with(None, {'configsvr': 'true',
                                              'bind_ip': '10.0.0.3,127.0.0.1',
                                              # 'keyFile': '/test/key/file',
                                              'dbpath': '/var/lib/mongodb'})
        self.assertTrue(self.manager.app.status.is_config_server)
        mock_set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(utils, 'poll_until')
    @mock.patch.object(service.MongoDBApp, 'start_db_with_conf_changes')
    @mock.patch.object(service.MongoDBApp, 'update_config_contents')
    @mock.patch.object(service.MongoDBApp, 'secure')
    @mock.patch.object(service.MongoDBApp, 'get_key_file',
                       return_value="/test/key/file")
    @mock.patch.object(netutils, 'get_my_ipv4', return_value="10.0.0.4")
    def test_prepare_member(self, mock_ip_address, mock_key_file,
                            mock_secure, mock_update, mock_start,
                            mock_poll, mock_set_status):
        self._prepare_method("test-id-3", "member", None)
        mock_update.assert_called_with(None,
                                       {'bind_ip': '10.0.0.4,127.0.0.1',
                                        # 'keyFile': '/test/key/file',
                                        'dbpath': '/var/lib/mongodb',
                                        'replSet': 'rs1'})
        mock_set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @mock.patch.object(service.MongoDBAppStatus, 'set_status')
    @mock.patch.object(utils, 'poll_until')
    @mock.patch.object(service.MongoDBApp, 'start_db_with_conf_changes')
    @mock.patch.object(service.MongoDBApp, 'update_config_contents')
    @mock.patch.object(service.MongoDBApp, 'secure')
    @mock.patch.object(netutils, 'get_my_ipv4', return_value="10.0.0.4")
    def test_prepare_secure(self, mock_ip_address, mock_secure,
                            mock_update, mock_start, mock_poll,
                            mock_set_status):
        key = "test_key"
        self._prepare_method("test-id-4", "member", key)
        mock_secure.assert_called_with(
            {"id": "test-id-4",
             "shard_id": "test_shard_id",
             "instance_type": 'member',
             "replica_set_name": "rs1",
             "key": key}

        )

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
