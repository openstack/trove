# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

import logging
from trove.backup.models import BackupState
from trove.common import cfg
from trove.common import context as trove_context
from trove.conductor import api as conductor_api
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.datastore.mysql.service import ADMIN_USER_NAME
from trove.guestagent.datastore.mysql.service import get_auth_password
from trove.guestagent.strategies.backup.base import BackupError
from trove.guestagent.strategies.backup.base import UnknownBackupType
from trove.guestagent.strategies.storage import get_storage_strategy
from trove.guestagent.strategies.backup import get_backup_strategy
from trove.guestagent.strategies.restore import get_restore_strategy

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

RUNNER = get_backup_strategy(CONF.backup_strategy,
                             CONF.backup_namespace)
EXTRA_OPTS = CONF.backup_runner_options.get(CONF.backup_strategy, '')


class BackupAgent(object):

    def _get_restore_runner(self, backup_type):
        """Returns the RestoreRunner associated with this backup type."""
        try:
            runner = get_restore_strategy(backup_type, CONF.restore_namespace)
        except ImportError:
            raise UnknownBackupType("Unknown Backup type: %s" % backup_type)
        return runner

    def execute_backup(self, context, backup_info,
                       runner=RUNNER, extra_opts=EXTRA_OPTS):
        backup_id = backup_info['id']
        ctxt = trove_context.TroveContext(
            user=CONF.nova_proxy_admin_user,
            auth_token=CONF.nova_proxy_admin_pass)
        conductor = conductor_api.API(ctxt)

        LOG.info("Running backup %s", backup_id)
        user = ADMIN_USER_NAME
        password = get_auth_password()
        storage = get_storage_strategy(
            CONF.storage_strategy,
            CONF.storage_namespace)(context)

        # Store the size of the filesystem before the backup.
        stats = get_filesystem_volume_stats(CONF.mount_point)
        backup = {
            'backup_id': backup_id,
            'size': stats.get('used', 0.0),
            'state': BackupState.BUILDING,
        }
        conductor.update_backup(CONF.guest_id, **backup)

        try:
            with runner(filename=backup_id, extra_opts=extra_opts,
                        user=user, password=password) as bkup:
                try:
                    LOG.info("Starting Backup %s", backup_id)
                    success, note, checksum, location = storage.save(
                        bkup.manifest,
                        bkup)

                    LOG.info("Backup %s completed status: %s", backup_id,
                             success)
                    LOG.info('Backup %s file swift checksum: %s',
                             backup_id, checksum)
                    LOG.info('Backup %s location: %s', backup_id,
                             location)

                    backup.update({
                        'checksum': checksum,
                        'location': location,
                        'note': note,
                        'backup_type': bkup.backup_type,
                    })

                    if not success:
                        raise BackupError(note)

                except Exception:
                    LOG.exception("Error saving %s Backup", backup_id)
                    backup.update({'state': BackupState.FAILED})
                    conductor.update_backup(CONF.guest_id, **backup)
                    raise

        except Exception:
            LOG.exception("Error running backup: %s", backup_id)
            backup.update({'state': BackupState.FAILED})
            conductor.update_backup(CONF.guest_id, **backup)
            raise
        else:
            LOG.info("Saving %s Backup Info to model", backup_id)
            backup.update({'state': BackupState.COMPLETED})
            conductor.update_backup(CONF.guest_id, **backup)

    def execute_restore(self, context, backup_info, restore_location):

        try:
            LOG.debug("Getting Restore Runner of type %s", backup_info['type'])
            restore_runner = self._get_restore_runner(backup_info['type'])

            LOG.debug("Getting Storage Strategy")
            storage = get_storage_strategy(
                CONF.storage_strategy,
                CONF.storage_namespace)(context)

            with restore_runner(storage, location=backup_info['location'],
                                checksum=backup_info['checksum'],
                                restore_location=restore_location) as runner:
                LOG.debug("Restoring instance from backup %s to %s",
                          backup_info['id'], restore_location)
                content_size = runner.restore()
                LOG.info("Restore from backup %s completed successfully to %s",
                         backup_info['id'], restore_location)
                LOG.info("Restore size: %s", content_size)

        except Exception as e:
            LOG.error(e)
            LOG.error("Error restoring backup %s", backup_info['id'])
            raise

        else:
            LOG.info("Restored Backup %s", backup_info['id'])
