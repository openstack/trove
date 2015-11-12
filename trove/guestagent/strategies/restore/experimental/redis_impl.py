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

from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.redis import service
from trove.guestagent.datastore.experimental.redis import system
from trove.guestagent.strategies.restore import base

LOG = logging.getLogger(__name__)


class RedisBackup(base.RestoreRunner):
    """Implementation of Restore Strategy for Redis."""
    __strategy_name__ = 'redisbackup'

    CONF_LABEL_AOF_TEMP_OFF = 'restore_aof_temp_off'
    INFO_PERSISTENCE_SECTION = 'persistence'

    def __init__(self, storage, **kwargs):
        self.app = service.RedisApp()
        self.restore_location = self.app.get_persistence_filepath()
        self.base_restore_cmd = 'tee %s' % self.restore_location
        self.aof_set = self.app.is_appendonly_enabled()
        self.aof_off_cfg = {'appendonly': 'no'}
        kwargs.update({'restore_location': self.restore_location})
        super(RedisBackup, self).__init__(storage, **kwargs)

    def pre_restore(self):
        self.app.stop_db()
        LOG.info(_("Cleaning out restore location: %s."),
                 self.restore_location)
        operating_system.chmod(self.restore_location, FileMode.SET_FULL,
                               as_root=True)
        utils.clean_out(self.restore_location)
        # IF AOF is set, we need to turn it off temporarily
        if self.aof_set:
            self.app.configuration_manager.apply_system_override(
                self.aof_off_cfg, change_id=self.CONF_LABEL_AOF_TEMP_OFF)

    def post_restore(self):
        operating_system.chown(self.restore_location,
                               system.REDIS_OWNER, system.REDIS_OWNER,
                               as_root=True)
        self.app.start_db()

        # IF AOF was set, we need to put back the original file
        if self.aof_set:
            self.app.admin.wait_until('loading', '0',
                                      section=self.INFO_PERSISTENCE_SECTION)
            self.app.admin.execute('BGREWRITEAOF')
            self.app.admin.wait_until('aof_rewrite_in_progress', '0',
                                      section=self.INFO_PERSISTENCE_SECTION)
            self.app.stop_db()
            self.app.configuration_manager.remove_system_override(
                change_id=self.CONF_LABEL_AOF_TEMP_OFF)
            self.app.start_db()
