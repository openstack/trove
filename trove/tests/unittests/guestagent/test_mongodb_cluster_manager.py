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

import testtools

from mock import patch
from trove.common import instance as ds_instance
from trove.common import utils
from trove.common.context import TroveContext
from trove.guestagent import volume
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mongodb import service as mongo_service
from trove.guestagent.datastore.mongodb.manager import Manager
from trove.guestagent.datastore.mongodb.service import MongoDBApp


class GuestAgentMongoDBClusterManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentMongoDBClusterManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = Manager()

    def tearDown(self):
        super(GuestAgentMongoDBClusterManagerTest, self).tearDown()

    @patch.object(mongo_service.MongoDbAppStatus, 'set_status')
    @patch.object(MongoDBApp, 'add_members', side_effect=RuntimeError("Boom!"))
    def test_add_members_failure(self, mock_add_members, mock_set_status):
        members = ["test1", "test2"]
        self.assertRaises(RuntimeError, self.manager.add_members,
                          self.context, members)
        mock_set_status.assert_called_with(ds_instance.ServiceStatuses.FAILED)

    @patch.object(utils, 'poll_until')
    @patch.object(MongoDBApp, 'do_mongo')
    def test_add_member(self, mock_do_mongo, mock_poll):
        members = ["test1", "test2"]
        self.manager.add_members(self.context, members)
        mock_do_mongo.assert_any_call("rs.initiate()")
        mock_do_mongo.assert_any_call("rs.add(\"test1\")")
        mock_do_mongo.assert_any_call("rs.add(\"test2\")")

    @patch.object(mongo_service.MongoDbAppStatus, 'set_status')
    @patch.object(MongoDBApp, 'add_shard', side_effect=RuntimeError("Boom!"))
    def test_add_shard_failure(self, mock_add_shard, mock_set_status):
        self.assertRaises(RuntimeError, self.manager.add_shard,
                          self.context, "rs", "rs_member")
        mock_set_status.assert_called_with(ds_instance.ServiceStatuses.FAILED)

    @patch.object(MongoDBApp, 'do_mongo')
    def test_add_shard(self, mock_do_mongo):
        self.manager.add_shard(self.context, "rs", "rs_member")
        mock_do_mongo.assert_called_with(
            "db.adminCommand({addShard: \"rs/rs_member:27017\"})")

    @patch.object(mongo_service.MongoDbAppStatus, 'set_status')
    @patch.object(MongoDBApp, 'add_config_servers',
                  side_effect=RuntimeError("Boom!"))
    def test_add_config_server_failure(self, mock_add_config,
                                       mock_set_status):
        self.assertRaises(RuntimeError, self.manager.add_config_servers,
                          self.context,
                          ["cfg_server1", "cfg_server2"])
        mock_set_status.assert_called_with(ds_instance.ServiceStatuses.FAILED)

    @patch.object(MongoDBApp, 'start_db_with_conf_changes')
    @patch.object(MongoDBApp, '_add_config_parameter', return_value="")
    @patch.object(MongoDBApp, '_delete_config_parameters', return_value="")
    @patch.object(MongoDBApp, '_read_config', return_value="")
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

    @patch.object(mongo_service.MongoDbAppStatus, 'set_status')
    @patch.object(MongoDBApp, 'write_mongos_upstart')
    @patch.object(MongoDBApp, 'reset_configuration')
    @patch.object(MongoDBApp, 'update_config_contents')
    @patch.object(operating_system, 'get_ip_address', return_value="10.0.0.2")
    def test_prepare_mongos(self, mock_ip_address, mock_update, mock_reset,
                            mock_upstart, mock_set_status):

        self._prepare_method("test-id-1", "query_router")
        mock_update.assert_called_with(None, {'bind_ip': '10.0.0.2'})
        self.assertTrue(self.manager.app.status.is_query_router)
        mock_set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @patch.object(mongo_service.MongoDbAppStatus, 'set_status')
    @patch.object(utils, 'poll_until')
    @patch.object(MongoDBApp, 'start_db_with_conf_changes')
    @patch.object(MongoDBApp, 'update_config_contents')
    @patch.object(operating_system, 'get_ip_address', return_value="10.0.0.3")
    def test_prepare_config_server(self, mock_ip_address, mock_update,
                                   mock_start, mock_poll, mock_set_status):
        self._prepare_method("test-id-2", "config_server")
        mock_update.assert_called_with(None, {'configsvr': 'true',
                                              'bind_ip': '10.0.0.3',
                                              'dbpath': '/var/lib/mongodb'})
        self.assertTrue(self.manager.app.status.is_config_server)
        mock_set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @patch.object(mongo_service.MongoDbAppStatus, 'set_status')
    @patch.object(utils, 'poll_until')
    @patch.object(MongoDBApp, 'start_db_with_conf_changes')
    @patch.object(MongoDBApp, 'update_config_contents')
    @patch.object(operating_system, 'get_ip_address', return_value="10.0.0.4")
    def test_prepare_member(self, mock_ip_address, mock_update, mock_start,
                            mock_poll, mock_set_status):
        self._prepare_method("test-id-3", "member")
        mock_update.assert_called_with(None,
                                       {'bind_ip': '10.0.0.4',
                                        'dbpath': '/var/lib/mongodb',
                                        'replSet': 'rs1'})
        mock_set_status.assert_called_with(
            ds_instance.ServiceStatuses.BUILD_PENDING)

    @patch.object(volume.VolumeDevice, 'mount_points', return_value=[])
    @patch.object(volume.VolumeDevice, 'mount', return_value=None)
    @patch.object(volume.VolumeDevice, 'migrate_data', return_value=None)
    @patch.object(volume.VolumeDevice, 'format', return_value=None)
    @patch.object(MongoDBApp, 'clear_storage')
    @patch.object(MongoDBApp, 'start_db')
    @patch.object(MongoDBApp, 'stop_db')
    @patch.object(MongoDBApp, 'install_if_needed')
    @patch.object(mongo_service.MongoDbAppStatus, 'begin_install')
    def _prepare_method(self, instance_id, instance_type, *args):
        cluster_config = {"id": instance_id,
                          "shard_id": "test_shard_id",
                          "instance_type": instance_type,
                          "replica_set_name": "rs1"}

        # invocation
        self.manager.prepare(context=self.context, databases=None,
                             packages=['package'],
                             memory_mb='2048', users=None,
                             mount_point='/var/lib/mongodb',
                             overrides=None,
                             cluster_config=cluster_config)
