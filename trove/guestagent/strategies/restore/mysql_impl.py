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
import pexpect
import tempfile

from trove.guestagent.strategies.restore import base
from trove.openstack.common import log as logging
from trove.common import exception
from trove.common import utils
import trove.guestagent.datastore.mysql.service as dbaas

LOG = logging.getLogger(__name__)


class MySQLRestoreMixin(object):
    """Common utils for restoring MySQL databases"""
    RESET_ROOT_RETRY_TIMEOUT = 100
    RESET_ROOT_SLEEP_INTERVAL = 10
    RESET_ROOT_MYSQL_COMMAND = ("SET PASSWORD FOR"
                                "'root'@'localhost'=PASSWORD('');")

    def mysql_is_running(self):
        if base.exec_with_root_helper("/usr/bin/mysqladmin", "ping"):
            LOG.info("The mysqld daemon is up and running.")
            return True
        else:
            LOG.info("The mysqld daemon is not running.")
            return False

    def mysql_is_not_running(self):
        if base.exec_with_root_helper("/usr/bin/pgrep", "mysqld"):
            LOG.info("The mysqld daemon is still running.")
            return False
        else:
            LOG.info("The mysqld daemon is not running.")
            return True

    def poll_until_then_raise(self, event, exc):
        try:
            utils.poll_until(event,
                             sleep_time=self.RESET_ROOT_SLEEP_INTERVAL,
                             time_out=self.RESET_ROOT_RETRY_TIMEOUT)
        except exception.PollTimeOut:
            raise exc

    def _spawn_with_init_file(self, temp_file):
        child = pexpect.spawn("sudo mysqld_safe --init-file=%s" %
                              temp_file.name)
        try:
            i = child.expect(['Starting mysqld daemon'])
            if i == 0:
                LOG.info("Starting mysqld daemon")
        except pexpect.TIMEOUT as e:
            LOG.error("wait_and_close_proc failed: %s" % e)
        finally:
            # There is a race condition here where we kill mysqld before
            # the init file been executed. We need to ensure mysqld is up.
            self.poll_until_then_raise(
                self.mysql_is_running,
                base.RestoreError("Reset root password failed: "
                                  "mysqld did not start!"))
            LOG.info("Root password reset successfully!")
            LOG.info("Cleaning up the temp mysqld process...")
            child.delayafterclose = 1
            child.delayafterterminate = 1
            child.close(force=True)
            utils.execute_with_timeout("sudo", "killall", "mysqld")
            self.poll_until_then_raise(
                self.mysql_is_not_running,
                base.RestoreError("Reset root password failed: "
                                  "mysqld did not stop!"))

    def reset_root_password(self):
        #Create temp file with reset root password
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(self.RESET_ROOT_MYSQL_COMMAND)
            fp.flush()
            utils.execute_with_timeout("sudo", "chmod", "a+r", fp.name)
            self._spawn_with_init_file(fp)


class MySQLDump(base.RestoreRunner, MySQLRestoreMixin):
    """Implementation of Restore Strategy for MySQLDump"""
    __strategy_name__ = 'mysqldump'
    base_restore_cmd = 'sudo mysql'


class InnoBackupEx(base.RestoreRunner, MySQLRestoreMixin):
    """Implementation of Restore Strategy for InnoBackupEx"""
    __strategy_name__ = 'innobackupex'
    base_restore_cmd = 'sudo xbstream -x -C %(restore_location)s'
    base_prepare_cmd = ('sudo innobackupex --apply-log %(restore_location)s'
                        ' --defaults-file=%(restore_location)s/backup-my.cnf'
                        ' --ibbackup xtrabackup 2>/tmp/innoprepare.log')

    def __init__(self, *args, **kwargs):
        super(InnoBackupEx, self).__init__(*args, **kwargs)
        self.prepare_cmd = self.base_prepare_cmd % kwargs
        self.prep_retcode = None

    def pre_restore(self):
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.stop_db()
        LOG.info("Cleaning out restore location: %s", self.restore_location)
        utils.execute_with_timeout("sudo", "chmod", "-R",
                                   "0777", self.restore_location)
        utils.clean_out(self.restore_location)

    def _run_prepare(self):
        LOG.info("Running innobackupex prepare: %s", self.prepare_cmd)
        self.prep_retcode = utils.execute(self.prepare_cmd, shell=True)
        LOG.info("Innobackupex prepare finished successfully")

    def post_restore(self):
        self._run_prepare()
        utils.execute_with_timeout("sudo", "chown", "-R", "-f",
                                   "mysql", self.restore_location)
        self._delete_old_binlogs()
        self.reset_root_password()
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.start_mysql()

    def _delete_old_binlogs(self):
        files = glob.glob(os.path.join(self.restore_location, "ib_logfile*"))
        for f in files:
            os.unlink(f)
