# Copyright 2026 PS Cloud Services
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

import json
import os

from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common import constants
from trove.guestagent.datastore.redis_common import manager
from trove.guestagent.strategies.replication import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class RedisReplicationBase(base.Replication):
    DATASTORE_NAME = 'redis'

    def _get_default_user_credentials(self, service):
        default_user_info = {
            'name': manager.REPLICATION_USER,
            'password': service.get_masterauth()
        }

        return default_user_info

    def enable_as_master(self, service, master_config):
        self._get_default_user_credentials(service)

    def snapshot_for_replication(self, context, service, adm, location,
                                 snapshot_info):
        LOG.info("Creating snapshot for replication")

        volumes_mapping = {
            f'/var/lib/{self.DATASTORE_NAME}': {
                'bind': f'/var/lib/{self.DATASTORE_NAME}', 'mode': 'rw'
            }
        }
        if snapshot_info.get('storage_driver') not in ["cinder"]:
            service.create_backup(context, snapshot_info,
                                  volumes_mapping=volumes_mapping,
                                  need_dbuser=False)

        replication_user = self._get_default_user_credentials(service)

        replica_conf = {
            'replication_user': replication_user
        }

        return snapshot_info['id'], replica_conf

    def get_master_ref(self, service, snapshot_info):
        ip_address = None
        if CONF.network_isolation and \
                os.path.exists(constants.ETH1_CONFIG_PATH):
            # Get IP_address from eth1.json, ipv4 address was preferred.
            with open(constants.ETH1_CONFIG_PATH) as fd:
                eth1_config = json.load(fd)
            ip_address = eth1_config.get("ipv4_address", None) or \
                eth1_config.get("ipv6_address", None)
        if not ip_address:
            ip_address = netutils.get_my_ipv4()
        master_ref = {
            'host': ip_address,
            'port': cfg.get_configuration_property('tcp_ports')[0]
        }
        return master_ref

    def enable_as_slave(self, service, snapshot, slave_config):
        LOG.debug("enable_as_slave")

        """Set up the replica server."""
        host = snapshot['master']['host']
        port = snapshot['master']['port'][0]
        password = snapshot['replica_conf']['replication_user']['password']
        name = snapshot['replica_conf']['replication_user']['name']
        conf = {
            'replicaof': [host, port],
            'masterauth': password,
            'masteruser': name,
        }
        service.configuration_manager.apply_system_override(conf)
        LOG.debug("replicaof is set in the config file: %s:%s",
                  snapshot['master']['host'],
                  snapshot['master']['port'])

        if service.status.is_running:
            service.adm.connection.config_set(
                "masteruser",
                snapshot['replica_conf']['replication_user']['name'])
            service.adm.connection.config_set(
                "masterauth",
                snapshot['replica_conf']['replication_user']['password'])
            service.adm.connection.slaveof(
                host=snapshot['master']['host'],
                port=snapshot['master']['port'][0])

    def detach_slave(self, service, for_failover):
        LOG.debug('detach_slave')
        service.adm.connection.slaveof(host=None, port=None)
        conf = {
            'replicaof': ['NO', 'ONE'],
            'masterauth': None,
            'masteruser': None,
        }
        service.configuration_manager.apply_system_override(conf)

    def get_replica_context(self, service, adm):
        """Running on primary."""
        default_user_info = self._get_default_user_credentials(service)

        return {
            'master': self.get_master_ref(None, None),
            'replica_conf': {'replication_user': default_user_info}
        }

    def cleanup_source_on_replica_detach(self, admin_service, replica_info):
        # No need to take any action here
        pass

    def demote_master(self, service):
        # No need to take any action here
        pass

    def backup_required_for_replication(self):
        """
        Indicates whether a backup is required for replication.
        Redis master will pass conf.d, ACL and SSL certificates to replicas
        within the volume backup data.
        """
        return True
