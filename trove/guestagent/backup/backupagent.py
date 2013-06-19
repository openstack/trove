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
from trove.backup.models import DBBackup
from trove.backup.models import BackupState
from trove.common import cfg, utils
from trove.guestagent.manager.mysql_service import ADMIN_USER_NAME
from trove.guestagent.manager.mysql_service import get_auth_password
from trove.guestagent.strategies.backup.base import BackupError
from trove.guestagent.strategies.backup.base import UnknownBackupType
from trove.guestagent.strategies.storage import get_storage_strategy
from trove.guestagent.strategies.backup import get_backup_strategy
from trove.guestagent.strategies.restore import get_restore_strategy

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

RUNNER = get_backup_strategy(CONF.backup_strategy,
                             CONF.backup_namespace)
BACKUP_CONTAINER = CONF.backup_swift_container


class BackupAgent(object):

    def _get_restore_runner(self, backup_type):
        """Returns the RestoreRunner associated with this backup type."""
        try:
            runner = get_restore_strategy(backup_type, CONF.restore_namespace)
        except ImportError:
            raise UnknownBackupType("Unknown Backup type: %s" % backup_type)
        return runner

    def execute_backup(self, context, backup_id, runner=RUNNER):
        LOG.debug("Searching for backup instance %s", backup_id)
        backup = DBBackup.find_by(id=backup_id)
        LOG.info("Setting task state to %s for instance %s",
                 BackupState.NEW, backup.instance_id)
        backup.state = BackupState.NEW
        backup.save()

        LOG.info("Running backup %s", backup_id)
        user = ADMIN_USER_NAME
        password = get_auth_password()
        swiftStorage = get_storage_strategy(
            CONF.storage_strategy,
            CONF.storage_namespace)(context)

        backup.state = BackupState.BUILDING
        backup.save()

        try:
            with runner(filename=backup_id, user=user, password=password)\
                    as bkup:
                LOG.info("Starting Backup %s", backup_id)
                success, note, checksum, location = swiftStorage.save(
                    BACKUP_CONTAINER,
                    bkup)

            LOG.info("Backup %s completed status: %s", backup_id, success)
            LOG.info("Backup %s file size: %s", backup_id, bkup.content_length)
            LOG.info('Backup %s file checksum: %s', backup_id, checksum)
            LOG.info('Backup %s location: %s', backup_id, location)

            if not success:
                raise BackupError(backup.note)

        except Exception as e:
            LOG.error(e)
            LOG.error("Error saving %s Backup", backup_id)
            backup.state = BackupState.FAILED
            backup.save()
            raise

        else:
            LOG.info("Saving %s Backup Info to model", backup_id)
            backup.state = BackupState.COMPLETED
            backup.checksum = checksum
            backup.location = location
            backup.note = note
            backup.backup_type = bkup.backup_type
            backup.save()

    def execute_restore(self, context, backup_id, restore_location):

        try:
            LOG.debug("Cleaning out restore location: %s", restore_location)
            utils.execute_with_timeout("sudo", "chmod", "-R",
                                       "0777", restore_location)
            utils.clean_out(restore_location)

            LOG.debug("Finding backup %s to restore", backup_id)
            backup = DBBackup.find_by(id=backup_id)

            LOG.debug("Getting Restore Runner of type %s", backup.backup_type)
            restore_runner = self._get_restore_runner(backup.backup_type)

            LOG.debug("Getting Storage Strategy")
            storage_strategy = get_storage_strategy(
                CONF.storage_strategy,
                CONF.storage_namespace)(context)

            LOG.debug("Preparing storage to download stream.")
            download_stream = storage_strategy.load(context,
                                                    backup.location,
                                                    restore_runner.is_zipped)

            with restore_runner(restore_stream=download_stream,
                                restore_location=restore_location) as runner:
                LOG.debug("Restoring instance from backup %s to %s",
                          backup_id, restore_location)
                content_size = runner.restore()
                LOG.info("Restore from backup %s completed successfully to %s",
                         backup_id, restore_location)
                LOG.info("Restore size: %s", content_size)

                utils.execute_with_timeout("sudo", "chown", "-R",
                                           "mysql", restore_location)

        except Exception as e:
            LOG.error(e)
            LOG.error("Error restoring backup %s", backup_id)
            raise

        else:
            LOG.info("Restored Backup %s", backup_id)
