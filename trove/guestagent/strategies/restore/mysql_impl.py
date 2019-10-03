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

    RESET_ROOT_MYSQL_COMMANDS = ("SET PASSWORD FOR "
                                 "'root'@'localhost'='';")
    # This is a suffix MySQL appends to the file name given in
    # the '--log-error' startup parameter.
    _ERROR_LOG_SUFFIX = '.err'
    _ERROR_MESSAGE_PATTERN = re.compile(b"ERROR")

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
            LOG.debug("MySQL is still running.")
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
        # This directory is added and removed by the mysql systemd service
        # as the database is started and stopped. The restore operation
        # takes place when the database is stopped, so the directory does
        # not exist, but it is assumed to exist by the mysqld_safe command
        # which starts the database. This command used to create this
        # directory if it didn't exist, but it was changed recently to
        # simply fail in this case.
        run_dir = "/var/run/mysqld"
        if not os.path.exists(run_dir):
            utils.execute("mkdir", run_dir,
                          run_as_root=True, root_helper="sudo")
        utils.execute("chown", "mysql:mysql", run_dir, err_log_file.name,
                      init_file.name, run_as_root=True, root_helper="sudo")
        command_mysql_safe = ("sudo mysqld_safe"
                              " --init-file=%s"
                              " --log-error=%s" %
                              (init_file.name, err_log_file.name))
        LOG.debug("Spawning: %s" % command_mysql_safe)
        child = pexpect.spawn(command_mysql_safe)
        try:
            index = child.expect(['Starting mysqld daemon'])
            if index == 0:
                LOG.info("Starting MySQL")
        except pexpect.TIMEOUT:
            LOG.exception("Got a timeout launching mysqld_safe")
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

            LOG.info("Root password reset successfully.")
            LOG.debug("Cleaning up the temp mysqld process.")
            utils.execute_with_timeout("mysqladmin", "-uroot",
                                       "--protocol=tcp", "shutdown")
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

        try:
            # Do not attempt to delete these files as the 'trove' user.
            # The process writing into it may have assumed its ownership.
            # Only owners can delete temporary files (restricted deletion).
            init_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
            operating_system.write_file(init_file.name,
                                        self.RESET_ROOT_MYSQL_COMMANDS)
            operating_system.chmod(init_file.name, FileMode.ADD_READ_ALL,
                                   as_root=True)
            err_log_file = tempfile.NamedTemporaryFile(
                suffix=self._ERROR_LOG_SUFFIX,
                delete=False)
            self._start_mysqld_safe_with_init_file(init_file, err_log_file)
        finally:
            init_file.close()
            err_log_file.close()
            operating_system.remove(
                init_file.name, force=True, as_root=True)
            operating_system.remove(
                err_log_file.name, force=True, as_root=True)

    def _find_first_error_message(self, fp):
        if self._is_non_zero_file(fp):
            return self._find_first_pattern_match(
                fp, self._ERROR_MESSAGE_PATTERN)
        return None

    def _is_non_zero_file(self, fp):
        file_path = fp.name
        return os.path.isfile(file_path) and (os.path.getsize(file_path) > 0)

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
    base_restore_cmd = ('sudo xbstream -x -C %(restore_location)s'
                        ' 2>/tmp/xbstream_extract.log')
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
        LOG.info("Cleaning out restore location: %s.",
                 self.restore_location)
        operating_system.chmod(self.restore_location, FileMode.SET_FULL,
                               as_root=True)
        utils.clean_out(self.restore_location)

    def _run_prepare(self):
        LOG.info("Running innobackupex prepare: %s.", self.prepare_cmd)
        self.prep_retcode = utils.execute(self.prepare_cmd, shell=True)
        LOG.info("Innobackupex prepare finished successfully.")

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

    def check_process(self):
        """Check whether xbstream restore is successful."""
        # We first check the restore process exits with 0, however
        # xbstream has a bug for creating new files:
        # https://jira.percona.com/browse/PXB-1542
        # So we also check the stderr with ignorance of some known
        # non-error log lines. Currently we only need to ignore:
        # "encryption: using gcrypt x.x.x"
        # After PXB-1542 is fixed, we could just check the exit status.
        LOG.debug('Checking return code of xbstream restore process.')
        return_code = self.process.wait()
        if return_code != 0:
            LOG.error('xbstream exited with %s', return_code)
            return False

        LOG.debug('Checking xbstream restore process stderr output.')
        IGNORE_LINES = [
            'encryption: using gcrypt ',
            'sudo: unable to resolve host ',
        ]
        with open('/tmp/xbstream_extract.log', 'r') as xbstream_log:
            for line in xbstream_log:
                # Ignore empty lines
                if not line.strip():
                    continue

                # Ignore known non-error log lines
                check_ignorance = [line.startswith(non_err)
                                   for non_err in IGNORE_LINES]
                if any(check_ignorance):
                    continue
                else:
                    LOG.error('xbstream restore failed with: %s',
                              line.rstrip('\n'))
                    return False

        return True


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
        LOG.info("Innobackupex prepare finished successfully.")

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
        """Run incremental restore.

        First grab all parents and prepare them with '--redo-only'. After
        all backups are restored the super class InnoBackupEx post_restore
        method is called to do the final prepare with '--apply-log'
        """
        self._incremental_restore(self.location, self.checksum)
        return self.content_length
