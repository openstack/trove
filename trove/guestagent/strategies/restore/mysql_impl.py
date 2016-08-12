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

import glob
import os
import re
import tempfile

from oslo_log import log as logging
import pexpect

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent.strategies.restore import base

LOG = logging.getLogger(__name__)


class MySQLRestoreMixin(object):
    """Common utils for restoring MySQL databases."""
    RESET_ROOT_RETRY_TIMEOUT = 100
    RESET_ROOT_SLEEP_INTERVAL = 10

    # Reset the root password in a single transaction with 'FLUSH PRIVILEGES'
    # to ensure we never leave database wide open without 'grant tables'.
    RESET_ROOT_MYSQL_COMMANDS = ("START TRANSACTION;",
                                 "UPDATE `mysql`.`user` SET"
                                 " `password`=PASSWORD('')"
                                 " WHERE `user`='root'"
                                 " AND `host` = 'localhost';",
                                 "FLUSH PRIVILEGES;",
                                 "COMMIT;")
    # This is a suffix MySQL appends to the file name given in
    # the '--log-error' startup parameter.
    _ERROR_LOG_SUFFIX = '.err'
    _ERROR_MESSAGE_PATTERN = re.compile("^ERROR:\s+.+$")

    def mysql_is_running(self):
        try:
            utils.execute_with_timeout("/usr/bin/mysqladmin", "ping")
            LOG.debug("MySQL is up and running.")
            return True
        except exception.ProcessExecutionError:
            LOG.debug("MySQL is not running.")
            return False

    def mysql_is_not_running(self):
        try:
            utils.execute_with_timeout("/usr/bin/pgrep", "mysqld")
            LOG.info(_("MySQL is still running."))
            return False
        except exception.ProcessExecutionError:
            LOG.debug("MySQL is not running.")
            return True

    def poll_until_then_raise(self, event, exc):
        try:
            utils.poll_until(event,
                             sleep_time=self.RESET_ROOT_SLEEP_INTERVAL,
                             time_out=self.RESET_ROOT_RETRY_TIMEOUT)
        except exception.PollTimeOut:
            raise exc

    def _start_mysqld_safe_with_init_file(self, init_file, err_log_file):
        child = pexpect.spawn("sudo mysqld_safe"
                              " --skip-grant-tables"
                              " --skip-networking"
                              " --init-file='%s'"
                              " --log-error='%s'" %
                              (init_file.name, err_log_file.name)
                              )
        try:
            i = child.expect(['Starting mysqld daemon'])
            if i == 0:
                LOG.info(_("Starting MySQL"))
        except pexpect.TIMEOUT:
            LOG.exception(_("Got a timeout launching mysqld_safe"))
        finally:
            # There is a race condition here where we kill mysqld before
            # the init file been executed. We need to ensure mysqld is up.
            #
            # mysqld_safe will start even if init-file statement(s) fail.
            # We therefore also check for errors in the log file.
            self.poll_until_then_raise(
                self.mysql_is_running,
                base.RestoreError("Reset root password failed:"
                                  " mysqld did not start!"))
            first_err_message = self._find_first_error_message(err_log_file)
            if first_err_message:
                raise base.RestoreError("Reset root password failed: %s"
                                        % first_err_message)

            LOG.info(_("Root password reset successfully."))
            LOG.debug("Cleaning up the temp mysqld process.")
            utils.execute_with_timeout("mysqladmin", "-uroot", "shutdown")
            LOG.debug("Polling for shutdown to complete.")
            try:
                utils.poll_until(self.mysql_is_not_running,
                                 sleep_time=self.RESET_ROOT_SLEEP_INTERVAL,
                                 time_out=self.RESET_ROOT_RETRY_TIMEOUT)
                LOG.debug("Database successfully shutdown")
            except exception.PollTimeOut:
                LOG.debug("Timeout shutting down database "
                          "- performing killall on mysqld_safe.")
                utils.execute_with_timeout("killall", "mysqld_safe",
                                           root_helper="sudo",
                                           run_as_root=True)
                self.poll_until_then_raise(
                    self.mysql_is_not_running,
                    base.RestoreError("Reset root password failed: "
                                      "mysqld did not stop!"))

    def reset_root_password(self):
        """Reset the password of the localhost root account used by Trove
        for initial datastore configuration.
        """

        with tempfile.NamedTemporaryFile(mode='w') as init_file:
            operating_system.chmod(init_file.name, FileMode.ADD_READ_ALL,
                                   as_root=True)
            self._writelines_one_per_line(init_file,
                                          self.RESET_ROOT_MYSQL_COMMANDS)
            # Do not attempt to delete the file as the 'trove' user.
            # The process writing into it may have assumed its ownership.
            # Only owners can delete temporary
            # files (restricted deletion).
            err_log_file = tempfile.NamedTemporaryFile(
                suffix=self._ERROR_LOG_SUFFIX,
                delete=False)
            try:
                self._start_mysqld_safe_with_init_file(init_file, err_log_file)
            finally:
                err_log_file.close()
                MySQLRestoreMixin._delete_file(err_log_file.name)

    def _writelines_one_per_line(self, fp, lines):
        fp.write(os.linesep.join(lines))
        fp.flush()

    def _find_first_error_message(self, fp):
        if MySQLRestoreMixin._is_non_zero_file(fp):
                return MySQLRestoreMixin._find_first_pattern_match(
                    fp,
                    self._ERROR_MESSAGE_PATTERN
                )
        return None

    @classmethod
    def _delete_file(self, file_path):
        """Force-remove a given file as root.
        Do not raise an exception on failure.
        """

        if os.path.isfile(file_path):
            try:
                operating_system.remove(file_path, force=True, as_root=True)
            except Exception:
                LOG.exception("Could not remove file: '%s'" % file_path)

    @classmethod
    def _is_non_zero_file(self, fp):
        file_path = fp.name
        return os.path.isfile(file_path) and (os.path.getsize(file_path) > 0)

    @classmethod
    def _find_first_pattern_match(self, fp, pattern):
        for line in fp:
            if pattern.match(line):
                return line
        return None


class MySQLDump(base.RestoreRunner, MySQLRestoreMixin):
    """Implementation of Restore Strategy for MySQLDump."""
    __strategy_name__ = 'mysqldump'
    base_restore_cmd = 'sudo mysql'


class InnoBackupEx(base.RestoreRunner, MySQLRestoreMixin):
    """Implementation of Restore Strategy for InnoBackupEx."""
    __strategy_name__ = 'innobackupex'
    base_restore_cmd = 'sudo xbstream -x -C %(restore_location)s'
    base_prepare_cmd = ('sudo innobackupex'
                        ' --defaults-file=%(restore_location)s/backup-my.cnf'
                        ' --ibbackup=xtrabackup'
                        ' --apply-log'
                        ' %(restore_location)s'
                        ' 2>/tmp/innoprepare.log')

    def __init__(self, *args, **kwargs):
        self._app = None
        super(InnoBackupEx, self).__init__(*args, **kwargs)
        self.prepare_cmd = self.base_prepare_cmd % kwargs
        self.prep_retcode = None

    @property
    def app(self):
        if self._app is None:
            self._app = self._build_app()
        return self._app

    def _build_app(self):
        return dbaas.MySqlApp(dbaas.MySqlAppStatus.get())

    def pre_restore(self):
        self.app.stop_db()
        LOG.info(_("Cleaning out restore location: %s."),
                 self.restore_location)
        operating_system.chmod(self.restore_location, FileMode.SET_FULL,
                               as_root=True)
        utils.clean_out(self.restore_location)

    def _run_prepare(self):
        LOG.debug("Running innobackupex prepare: %s.", self.prepare_cmd)
        self.prep_retcode = utils.execute(self.prepare_cmd, shell=True)
        LOG.info(_("Innobackupex prepare finished successfully."))

    def post_restore(self):
        self._run_prepare()
        operating_system.chown(self.restore_location, 'mysql', None,
                               force=True, as_root=True)
        self._delete_old_binlogs()
        self.reset_root_password()
        self.app.start_mysql()

    def _delete_old_binlogs(self):
        files = glob.glob(os.path.join(self.restore_location, "ib_logfile*"))
        for f in files:
            os.unlink(f)


class InnoBackupExIncremental(InnoBackupEx):
    __strategy_name__ = 'innobackupexincremental'
    incremental_prep = ('sudo innobackupex'
                        ' --defaults-file=%(restore_location)s/backup-my.cnf'
                        ' --ibbackup=xtrabackup'
                        ' --apply-log'
                        ' --redo-only'
                        ' %(restore_location)s'
                        ' %(incremental_args)s'
                        ' 2>/tmp/innoprepare.log')

    def __init__(self, *args, **kwargs):
        super(InnoBackupExIncremental, self).__init__(*args, **kwargs)
        self.restore_location = kwargs.get('restore_location')
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
        LOG.debug("Running innobackupex prepare: %s.", prepare_cmd)
        utils.execute(prepare_cmd, shell=True)
        LOG.info(_("Innobackupex prepare finished successfully."))

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
            LOG.info(_("Restoring parent: %(parent_location)s"
                       " checksum: %(parent_checksum)s.") % metadata)
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
        """Run incremental restore.

        First grab all parents and prepare them with '--redo-only'. After
        all backups are restored the super class InnoBackupEx post_restore
        method is called to do the final prepare with '--apply-log'
        """
        self._incremental_restore(self.location, self.checksum)
        return self.content_length
