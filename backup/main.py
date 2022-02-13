# Copyright 2020 Catalyst Cloud
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

import os

import sys

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

topdir = os.path.normpath(
    os.path.join(os.path.abspath(sys.argv[0]), os.pardir, os.pardir))
sys.path.insert(0, topdir)

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

cli_opts = [
    cfg.StrOpt('backup-id'),
    cfg.StrOpt(
        'storage-driver',
        default='swift',
        choices=['swift']
    ),
    cfg.StrOpt(
        'driver',
        default='innobackupex',
        choices=['innobackupex', 'mariabackup', 'pg_basebackup', 'xtrabackup']
    ),
    cfg.BoolOpt('backup'),
    cfg.StrOpt(
        'backup-encryption-key',
        help='This is only for backward compatibility. The backups '
             'created prior to Victoria may be encrypted. Trove guest '
             'agent is responsible for passing the key.'
    ),
    cfg.StrOpt('db-user'),
    cfg.StrOpt('db-password'),
    cfg.StrOpt('db-host'),
    cfg.StrOpt('db-datadir'),
    cfg.StrOpt('os-token'),
    cfg.StrOpt('os-auth-url'),
    cfg.StrOpt('os-tenant-id'),
    cfg.StrOpt('swift-container', default='database_backups'),
    cfg.DictOpt('swift-extra-metadata'),
    cfg.StrOpt('restore-from'),
    cfg.StrOpt('restore-checksum'),
    cfg.BoolOpt('incremental'),
    cfg.StrOpt('parent-location'),
    cfg.StrOpt(
        'parent-checksum',
        help='It is up to the storage driver to decide to validate the '
             'checksum or not. '
    ),
    cfg.StrOpt('pg-wal-archive-dir'),
]

driver_mapping = {
    'innobackupex': 'backup.drivers.innobackupex.InnoBackupEx',
    'innobackupex_inc': 'backup.drivers.innobackupex.InnoBackupExIncremental',
    'mariabackup': 'backup.drivers.mariabackup.MariaBackup',
    'mariabackup_inc': 'backup.drivers.mariabackup.MariaBackupIncremental',
    'pg_basebackup': 'backup.drivers.postgres.PgBasebackup',
    'pg_basebackup_inc': 'backup.drivers.postgres.PgBasebackupIncremental',
    'xtrabackup': 'backup.drivers.xtrabackup.XtraBackup',
    'xtrabackup_inc': 'backup.drivers.xtrabackup.XtraBackupIncremental'
}
storage_mapping = {
    'swift': 'backup.storage.swift.SwiftStorage',
}


def stream_backup_to_storage(runner_cls, storage):
    parent_metadata = {}
    extra_params = {}

    if CONF.incremental:
        if not CONF.parent_location:
            LOG.error('--parent-location should be provided for incremental '
                      'backup')
            exit(1)

        parent_metadata = storage.load_metadata(CONF.parent_location,
                                                CONF.parent_checksum)
        parent_metadata.update(
            {
                'parent_location': CONF.parent_location,
                'parent_checksum': CONF.parent_checksum
            }
        )

    if CONF.pg_wal_archive_dir:
        extra_params['wal_archive_dir'] = CONF.pg_wal_archive_dir

    extra_params.update(parent_metadata)

    try:
        with runner_cls(filename=CONF.backup_id, **extra_params) as bkup:
            checksum, location = storage.save(
                bkup,
                metadata=CONF.swift_extra_metadata,
                container=CONF.swift_container
            )
        LOG.info('Backup successfully, checksum: %s, location: %s',
                 checksum, location)
    except Exception as err:
        LOG.exception('Failed to call stream_backup_to_storage, error: %s',
                      err)


def stream_restore_from_storage(runner_cls, storage):
    params = {
        'storage': storage,
        'location': CONF.restore_from,
        'checksum': CONF.restore_checksum,
        'wal_archive_dir': CONF.pg_wal_archive_dir,
        'lsn': None
    }

    if storage.is_incremental_backup(CONF.restore_from):
        params['lsn'] = storage.get_backup_lsn(CONF.restore_from)

    try:
        runner = runner_cls(**params)
        restore_size = runner.restore()
        LOG.info('Restore successfully, restore_size: %s', restore_size)
    except Exception as err:
        LOG.exception('Failed to call stream_restore_from_storage, error: %s',
                      err)


def main():
    CONF.register_cli_opts(cli_opts)
    logging.register_options(CONF)
    CONF(sys.argv[1:], project='trove-backup')
    logging.setup(CONF, 'trove-backup')

    runner_cls = importutils.import_class(driver_mapping[CONF.driver])
    storage = importutils.import_class(storage_mapping[CONF.storage_driver])()

    if CONF.backup:
        if CONF.incremental:
            runner_cls = importutils.import_class(
                driver_mapping['%s_inc' % CONF.driver])

        LOG.info('Starting backup database to %s, backup ID %s',
                 CONF.storage_driver, CONF.backup_id)
        stream_backup_to_storage(runner_cls, storage)
    else:
        if storage.is_incremental_backup(CONF.restore_from):
            LOG.debug('Restore from incremental backup')
            runner_cls = importutils.import_class(
                driver_mapping['%s_inc' % CONF.driver])

        LOG.info('Starting restore database from %s, location: %s',
                 CONF.storage_driver, CONF.restore_from)

        stream_restore_from_storage(runner_cls, storage)


if __name__ == '__main__':
    sys.exit(main())
