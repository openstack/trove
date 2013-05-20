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
from reddwarf.guestagent.strategy import Strategy
from reddwarf.common import cfg, utils
from reddwarf.openstack.common import log as logging
from eventlet.green import subprocess
import tempfile
import pexpect
import os
import glob

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CHUNK_SIZE = CONF.backup_chunk_size
RESET_ROOT_MYSQL_COMMAND = """
UPDATE mysql.user SET Password=PASSWORD('') WHERE User='root';
FLUSH PRIVILEGES;
"""


class RestoreError(Exception):
    """Error running the Backup Command."""


class RestoreRunner(Strategy):
    """ Base class for Restore Strategy implementations """
    """Restore a database from a previous backup."""

    __strategy_type__ = 'restore_runner'
    __strategy_ns__ = 'reddwarf.guestagent.strategies.restore'

    # The actual system calls to run the restore and prepare
    restore_cmd = None
    prepare_cmd = None

    # The backup format type
    restore_type = None

    def __init__(self, restore_stream, **kwargs):
        self.restore_stream = restore_stream
        self.restore_location = kwargs.get('restore_location',
                                           '/var/lib/mysql')
        self.restore_cmd = self.restore_cmd % kwargs
        self.prepare_cmd = self.prepare_cmd % kwargs \
            if hasattr(self, 'prepare_cmd') else None
        super(RestoreRunner, self).__init__()

    def __enter__(self):
        """Return the runner"""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Clean up everything."""
        if exc_type is not None:
            return False

        if hasattr(self, 'process'):
            try:
                self.process.terminate()
            except OSError:
                # Already stopped
                pass
            utils.raise_if_process_errored(self.process, RestoreError)

        return True

    def restore(self):
        self._pre_restore()
        content_length = self._run_restore()
        self._run_prepare()
        self._post_restore()
        return content_length

    def _run_restore(self):
        with self.restore_stream as stream:
            self.process = subprocess.Popen(self.restore_cmd, shell=True,
                                            stdin=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
            self.pid = self.process.pid
            content_length = 0
            chunk = stream.read(CHUNK_SIZE)
            while chunk:
                self.process.stdin.write(chunk)
                content_length += len(chunk)
                chunk = stream.read(CHUNK_SIZE)
            self.process.stdin.close()
            LOG.info("Restored %s bytes from swift via xbstream."
                     % content_length)

        return content_length

    def _run_prepare(self):
        if hasattr(self, 'prepare_cmd'):
            LOG.info("Running innobackupex prepare...")
            self.prep_retcode = utils.execute(self.prepare_cmd,
                                              shell=True)
            LOG.info("Innobackupex prepare finished successfully")

    def _spawn_with_init_file(self, temp_file):
        child = pexpect.spawn("sudo mysqld_safe --init-file=%s" %
                              temp_file.name)
        try:
            i = child.expect(['Starting mysqld daemon'])
            if i == 0:
                LOG.info("Root password reset successfully!")
        except pexpect.TIMEOUT as e:
            LOG.error("wait_and_close_proc failed: %s" % e)
        finally:
            LOG.info("Cleaning up the temp mysqld process...")
            child.delayafterclose = 1
            child.delayafterterminate = 1
            child.close(force=True)
            utils.execute_with_timeout("sudo", "killall", "mysqld")

    def _reset_root_password(self):
        #Create temp file with reset root password
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(RESET_ROOT_MYSQL_COMMAND)
            fp.flush()
            utils.execute_with_timeout("sudo", "chmod", "a+r", fp.name)
            self._spawn_with_init_file(fp)

    def _delete_old_binlogs(self):
        filelist = glob.glob(self.restore_location + "/ib_logfile*")
        for f in filelist:
            os.unlink(f)
