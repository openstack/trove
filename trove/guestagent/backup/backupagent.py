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

from oslo_log import log as logging

from trove.backup.state import BackupState
from trove.common import cfg
from trove.common.i18n import _
from trove.common.strategies.storage import get_storage_strategy
from trove.conductor import api as conductor_api
from trove.guestagent.common import timeutils
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.strategies.backup.base import BackupError
from trove.guestagent.strategies.backup.base import UnknownBackupType
from trove.guestagent.strategies.backup import get_backup_strategy
from trove.guestagent.strategies.restore import get_restore_strategy

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

CONFIG_MANAGER = CONF.get('mysql'
                          if not CONF.datastore_manager
                          else CONF.datastore_manager)

STRATEGY = CONFIG_MANAGER.backup_strategy
BACKUP_NAMESPACE = CONFIG_MANAGER.backup_namespace
RESTORE_NAMESPACE = CONFIG_MANAGER.restore_namespace
RUNNER = get_backup_strategy(STRATEGY, BACKUP_NAMESPACE)
EXTRA_OPTS = CONF.backup_runner_options.get(STRATEGY, '')

# Try to get the incremental strategy or return the default 'backup_strategy'
INCREMENTAL = CONFIG_MANAGER.backup_incremental_strategy.get(
    STRATEGY, STRATEGY)

INCREMENTAL_RUNNER = get_backup_strategy(INCREMENTAL, BACKUP_NAMESPACE)


class BackupAgent(object):
    def _get_restore_runner(self, backup_type):
        """Returns the RestoreRunner associated with this backup type."""
        try:
            runner = get_restore_strategy(backup_type, RESTORE_NAMESPACE)
        except ImportError:
            raise UnknownBackupType("Unknown Backup type: %s in namespace %s"
                                    % (backup_type, RESTORE_NAMESPACE))
        return runner

    def stream_backup_to_storage(self, context, backup_info, runner, storage,
                                 parent_metadata={}, extra_opts=EXTRA_OPTS):
        backup_id = backup_info['id']
        conductor = conductor_api.API(context)

        # Store the size of the filesystem before the backup.
        mount_point = CONFIG_MANAGER.mount_point
        stats = get_filesystem_volume_stats(mount_point)
        backup_state = {
            'backup_id': backup_id,
            'size': stats.get('used', 0.0),
            'state': BackupState.BUILDING,
        }
        conductor.update_backup(CONF.guest_id,
                                sent=timeutils.float_utcnow(),
                                **backup_state)
        LOG.debug("Updated state for %s to %s.", backup_id, backup_state)

        with runner(filename=backup_id, extra_opts=extra_opts,
                    **parent_metadata) as bkup:
            try:
                LOG.debug("Starting backup %s.", backup_id)
                success, note, checksum, location = storage.save(
                    bkup.manifest,
                    bkup)

                backup_state.update({
                    'checksum': checksum,
                    'location': location,
                    'note': note,
                    'success': success,
                    'backup_type': bkup.backup_type,
                })

                LOG.debug("Backup %(backup_id)s completed status: "
                          "%(success)s.", backup_state)
                LOG.debug("Backup %(backup_id)s file swift checksum: "
                          "%(checksum)s.", backup_state)
                LOG.debug("Backup %(backup_id)s location: "
                          "%(location)s.", backup_state)

                if not success:
                    raise BackupError(note)

                meta = bkup.metadata()
                meta['datastore'] = backup_info['datastore']
                meta['datastore_version'] = backup_info[
                    'datastore_version']
                storage.save_metadata(location, meta)

                backup_state.update({'state': BackupState.COMPLETED})

                return meta

            except Exception:
                LOG.exception(
                    _("Error saving backup: %(backup_id)s.") % backup_state)
                backup_state.update({'state': BackupState.FAILED})
                raise
            finally:
                LOG.info(_("Completed backup %(backup_id)s.") % backup_state)
                conductor.update_backup(CONF.guest_id,
                                        sent=timeutils.float_utcnow(),
                                        **backup_state)
                LOG.debug("Updated state for %s to %s.",
                          backup_id, backup_state)

    def execute_backup(self, context, backup_info,
                       runner=RUNNER, extra_opts=EXTRA_OPTS,
                       incremental_runner=INCREMENTAL_RUNNER):

        LOG.debug("Running backup %(id)s.", backup_info)
        storage = get_storage_strategy(
            CONF.storage_strategy,
            CONF.storage_namespace)(context)

        # Check if this is an incremental backup and grab the parent metadata
        parent_metadata = {}
        if backup_info.get('parent'):
            runner = incremental_runner
            LOG.debug("Using incremental backup runner: %s.", runner.__name__)
            parent = backup_info['parent']
            parent_metadata = storage.load_metadata(parent['location'],
                                                    parent['checksum'])
            # The parent could be another incremental backup so we need to
            # reset the location and checksum to *this* parents info
            parent_metadata.update({
                'parent_location': parent['location'],
                'parent_checksum': parent['checksum']
            })

        self.stream_backup_to_storage(context, backup_info, runner, storage,
                                      parent_metadata, extra_opts)

    def execute_restore(self, context, backup_info, restore_location):

        try:
            LOG.debug("Getting Restore Runner %(type)s.", backup_info)
            restore_runner = self._get_restore_runner(backup_info['type'])

            LOG.debug("Getting Storage Strategy.")
            storage = get_storage_strategy(
                CONF.storage_strategy,
                CONF.storage_namespace)(context)

            runner = restore_runner(storage, location=backup_info['location'],
                                    checksum=backup_info['checksum'],
                                    restore_location=restore_location)
            backup_info['restore_location'] = restore_location
            LOG.debug("Restoring instance from backup %(id)s to "
                      "%(restore_location)s.", backup_info)
            content_size = runner.restore()
            LOG.debug("Restore from backup %(id)s completed successfully "
                      "to %(restore_location)s.", backup_info)
            LOG.debug("Restore size: %s.", content_size)

        except Exception:
            LOG.exception(_("Error restoring backup %(id)s.") % backup_info)
            raise

        else:
            LOG.debug("Restored backup %(id)s." % backup_info)
