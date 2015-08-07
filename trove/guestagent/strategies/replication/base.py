# Copyright 2014 Tesora, Inc.
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
#

import abc

import six
from trove.guestagent.strategy import Strategy


@six.add_metaclass(abc.ABCMeta)
class Replication(Strategy):
    """Base class for Replication Strategy implementation."""

    __strategy_type__ = 'replication'
    __strategy_ns__ = 'trove.guestagent.strategies.replication'

    def __init__(self, context):
        self.context = context
        super(Replication, self).__init__()

    @abc.abstractmethod
    def get_master_ref(self, service, snapshot_info):
        """Get reference to master site for replication strategy."""

    def backup_required_for_replication(self):
        """Indicates whether a backup is required for replication."""
        return True

    @abc.abstractmethod
    def snapshot_for_replication(self, context, service, location,
                                 snapshot_info):
        """Capture snapshot of master db."""

    @abc.abstractmethod
    def enable_as_master(self, service, master_config):
        """Configure underlying database to act as master for replication."""

    @abc.abstractmethod
    def enable_as_slave(self, service, snapshot, slave_config):
        """Configure underlying database as a slave of the given master."""

    @abc.abstractmethod
    def detach_slave(self, service, for_failover):
        """Turn off replication on a slave site."""

    @abc.abstractmethod
    def cleanup_source_on_replica_detach(self, service, replica_info):
        """Clean up the source on the detach of a replica."""

    @abc.abstractmethod
    def demote_master(self, service):
        """Turn off replication on a master site."""
