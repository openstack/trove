# Copyright 2015 Hewlett-Packard Development Company, L.P. and Tesora, Inc
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

from oslo_log import log as logging

from trove.guestagent.datastore.experimental.redis import service
from trove.guestagent.strategies.backup import base

LOG = logging.getLogger(__name__)


class RedisBackup(base.BackupRunner):
    """Implementation of Backup Strategy for Redis."""
    __strategy_name__ = 'redisbackup'

    def __init__(self, filename, **kwargs):
        self.app = service.RedisApp()
        super(RedisBackup, self).__init__(filename, **kwargs)

    @property
    def cmd(self):
        cmd = 'sudo cat %s' % self.app.get_persistence_filepath()
        return cmd + self.zip_cmd + self.encrypt_cmd

    def _run_pre_backup(self):
        self.app.admin.persist_data()
        LOG.debug('Redis data persisted.')
