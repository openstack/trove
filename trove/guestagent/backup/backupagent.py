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
from trove.guestagent.common import timeutils
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.strategies.backup.base import BackupError
from trove.guestagent.strategies.backup.base import UnknownBackupType
from trove.guestagent.strategies.storage import get_storage_strategy
from trove.guestagent.strategies.backup import get_backup_strategy
from trove.guestagent.strategies.restore import get_restore_strategy
from trove.openstack.common.gettextutils import _  # noqa

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

MANAGER = CONF.datastore_manager
# If datastore manager is not mentioned in guest
# configuration file, would be used mysql as datastore_manager by the default
STRATEGY = CONF.get('mysql' if not MANAGER else MANAGER).backup_strategy
NAMESPACE = CONF.backup_namespace

RUNNER = get_backup_strategy(STRATEGY, NAMESPACE)
EXTRA_OPTS = CONF.backup_runner_options.get(STRATEGY, '')

# Try to get the incremental strategy or return the default 'backup_strategy'
INCREMENTAL = CONF.backup_incremental_strategy.get(STRATEGY,
                                                   STRATEGY)

INCREMENTAL_RUNNER = get_backup_strategy(INCREMENTAL, NAMESPACE)


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

        LOG.info(_("Running backup %(id)s") % backup_info)
        storage = get_storage_strategy(
            CONF.storage_strategy,
            CONF.storage_namespace)(context)

        # Check if this is an incremental backup and grab the parent metadata
        parent_metadata = {}
        if backup_info.get('parent'):
            runner = INCREMENTAL_RUNNER
            LOG.info(_("Using incremental runner: %s") % runner.__name__)
            parent = backup_info['parent']
            parent_metadata = storage.load_metadata(parent['location'],
                                                    parent['checksum'])
            # The parent could be another incremental backup so we need to
            # reset the location and checksum to *this* parents info
            parent_metadata.update({
                'parent_location': parent['location'],
                'parent_checksum': parent['checksum']
            })

        # Store the size of the filesystem before the backup.
        mount_point = CONF.get('mysql' if not CONF.datastore_manager
                               else CONF.datastore_manager).mount_point
        stats = get_filesystem_volume_stats(mount_point)
        backup = {
            'backup_id': backup_id,
            'size': stats.get('used', 0.0),
            'state': BackupState.BUILDING,
        }
        conductor.update_backup(CONF.guest_id,
                                sent=timeutils.float_utcnow(),
                                **backup)

        try:
            with runner(filename=backup_id, extra_opts=extra_opts,
                        **parent_metadata) as bkup:
                try:
                    LOG.info(_("Starting Backup %s"), backup_id)
                    success, note, checksum, location = storage.save(
                        bkup.manifest,
                        bkup)

                    backup.update({
                        'checksum': checksum,
                        'location': location,
                        'note': note,
                        'success': success,
                        'backup_type': bkup.backup_type,
                    })

                    LOG.info(_("Backup %(backup_id)s completed status: "
                               "%(success)s") % backup)
                    LOG.info(_("Backup %(backup_id)s file swift checksum: "
                               "%(checksum)s") % backup)
                    LOG.info(_("Backup %(backup_id)s location: "
                               "%(location)s") % backup)

                    if not success:
                        raise BackupError(note)

                    storage.save_metadata(location, bkup.metadata())

                except Exception:
                    LOG.exception(_("Error saving %(backup_id)s Backup") %
                                  backup)
                    backup.update({'state': BackupState.FAILED})
                    conductor.update_backup(CONF.guest_id,
                                            sent=timeutils.float_utcnow(),
                                            **backup)
                    raise

        except Exception:
            LOG.exception(_("Error running backup: %(backup_id)s") % backup)
            backup.update({'state': BackupState.FAILED})
            conductor.update_backup(CONF.guest_id,
                                    sent=timeutils.float_utcnow(),
                                    **backup)
            raise
        else:
            LOG.info(_("Saving %(backup_id)s Backup Info to model") % backup)
            backup.update({'state': BackupState.COMPLETED})
            conductor.update_backup(CONF.guest_id,
                                    sent=timeutils.float_utcnow(),
                                    **backup)

    def execute_restore(self, context, backup_info, restore_location):

        try:
            LOG.debug(_("Getting Restore Runner %(type)s"), backup_info)
            restore_runner = self._get_restore_runner(backup_info['type'])

            LOG.debug("Getting Storage Strategy")
            storage = get_storage_strategy(
                CONF.storage_strategy,
                CONF.storage_namespace)(context)

            runner = restore_runner(storage, location=backup_info['location'],
                                    checksum=backup_info['checksum'],
                                    restore_location=restore_location)
            backup_info['restore_location'] = restore_location
            LOG.debug(_("Restoring instance from backup %(id)s to "
                        "%(restore_location)s") % backup_info)
            content_size = runner.restore()
            LOG.info(_("Restore from backup %(id)s completed successfully "
                       "to %(restore_location)s") % backup_info)
            LOG.info(_("Restore size: %s") % content_size)

        except Exception as e:
            LOG.error(e)
            LOG.error(_("Error restoring backup %(id)s") % backup_info)
            raise

        else:
            LOG.info(_("Restored Backup %(id)s") % backup_info)
