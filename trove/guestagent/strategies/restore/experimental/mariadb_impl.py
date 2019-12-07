# Copyright 2019 Catalyst Cloud Ltd.
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
import glob
import os

from oslo_log import log as logging

from trove.common import cfg
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mariadb import service
from trove.guestagent.datastore.mysql_common import service as mysql_service
from trove.guestagent.strategies.restore import base
from trove.guestagent.strategies.restore import mysql_impl

LOG = logging.getLogger(__name__)
PREPARE_LOG = '/tmp/innoprepare.log'


class MariaBackup(base.RestoreRunner, mysql_impl.MySQLRestoreMixin):
    __strategy_name__ = 'mariabackup'
    base_restore_cmd = ('sudo mbstream -x -C %(restore_location)s '
                        '2>/tmp/xbstream_extract.log')

    def __init__(self, *args, **kwargs):
        self._app = None
        super(MariaBackup, self).__init__(*args, **kwargs)

    @property
    def app(self):
        if self._app is None:
            self._app = service.MariaDBApp(
                mysql_service.BaseMySqlAppStatus.get()
            )
        return self._app

    def pre_restore(self):
        self.app.stop_db()
        LOG.debug("Cleaning out restore location: %s.", self.restore_location)
        operating_system.chmod(self.restore_location,
                               operating_system.FileMode.SET_FULL,
                               as_root=True)
        utils.clean_out(self.restore_location)

    def post_restore(self):
        operating_system.chown(self.restore_location, 'mysql', None,
                               force=True, as_root=True)

        # When using Mariabackup from versions prior to MariaDB 10.2.10, you
        # would also have to remove any pre-existing InnoDB redo log files.
        self._delete_old_binlogs()
        self.app.start_mysql()
        LOG.debug("Finished post restore.")

    def _delete_old_binlogs(self):
        files = glob.glob(os.path.join(self.restore_location, "ib_logfile*"))
        for f in files:
            os.unlink(f)

    def check_process(self):
        LOG.debug('Checking return code of mbstream restore process.')
        return_code = self.process.wait()
        if return_code != 0:
            LOG.error('mbstream exited with %s', return_code)
            return False

        return True


class MariaBackupIncremental(MariaBackup):
    __strategy_name__ = 'mariabackupincremental'
    incremental_prep = ('sudo mariabackup --prepare '
                        '--target-dir=%(restore_location)s '
                        '%(incremental_args)s '
                        '2>/tmp/innoprepare.log')

    def __init__(self, *args, **kwargs):
        super(MariaBackupIncremental, self).__init__(*args, **kwargs)
        self.content_length = 0

    def _incremental_restore_cmd(self, incremental_dir):
        """Return a command for a restore with a incremental location."""
        args = {'restore_location': incremental_dir}
        return (self.decrypt_cmd +
                self.unzip_cmd +
                (self.base_restore_cmd % args))

    def _incremental_prepare_cmd(self, incremental_dir):
        if incremental_dir is not None:
            incremental_arg = '--incremental-dir=%s' % incremental_dir
        else:
            incremental_arg = ''

        args = {
            'restore_location': self.restore_location,
            'incremental_args': incremental_arg,
        }

        return self.incremental_prep % args

    def _incremental_prepare(self, incremental_dir):
        prepare_cmd = self._incremental_prepare_cmd(incremental_dir)

        LOG.debug("Running mariabackup prepare: %s.", prepare_cmd)
        utils.execute(prepare_cmd, shell=True)
        LOG.debug("mariabackup prepare finished successfully.")

    def _incremental_restore(self, location, checksum):
        """Recursively apply backups from all parents.
        If we are the parent then we restore to the restore_location and
        we apply the logs to the restore_location only.
        Otherwise if we are an incremental we restore to a subfolder to
        prevent stomping on the full restore data. Then we run apply log
        with the '--incremental-dir' flag
        """
        metadata = self.storage.load_metadata(location, checksum)
        incremental_dir = None
        if 'parent_location' in metadata:
            LOG.info("Restoring parent: %(parent_location)s"
                     " checksum: %(parent_checksum)s.", metadata)
            parent_location = metadata['parent_location']
            parent_checksum = metadata['parent_checksum']
            # Restore parents recursively so backup are applied sequentially
            self._incremental_restore(parent_location, parent_checksum)
            # for *this* backup set the incremental_dir
            # just use the checksum for the incremental path as it is
            # sufficiently unique /var/lib/mysql/<checksum>
            incremental_dir = os.path.join(
                cfg.get_configuration_property('mount_point'), checksum)
            operating_system.create_directory(incremental_dir, as_root=True)
            command = self._incremental_restore_cmd(incremental_dir)
        else:
            # The parent (full backup) use the same command from InnobackupEx
            # super class and do not set an incremental_dir.
            command = self.restore_cmd

        self.content_length += self._unpack(location, checksum, command)
        self._incremental_prepare(incremental_dir)

        # Delete unpacked incremental backup metadata
        if incremental_dir:
            operating_system.remove(incremental_dir, force=True, as_root=True)

    def _run_restore(self):
        """Run incremental restore."""
        self._incremental_restore(self.location, self.checksum)
        return self.content_length
