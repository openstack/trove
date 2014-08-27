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
import os
import signal

from eventlet.green import subprocess
from trove.common import cfg, utils
from trove.guestagent.strategy import Strategy
from trove.openstack.common import log as logging

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class BackupError(Exception):
    """Error running the Backup Command."""


class UnknownBackupType(Exception):
    """Unknown backup type."""


class BackupRunner(Strategy):
    """Base class for Backup Strategy implementations."""
    __strategy_type__ = 'backup_runner'
    __strategy_ns__ = 'trove.guestagent.strategies.backup'

    # The actual system call to run the backup
    cmd = None
    is_zipped = CONF.backup_use_gzip_compression
    is_encrypted = CONF.backup_use_openssl_encryption
    encrypt_key = CONF.backup_aes_cbc_key

    def __init__(self, filename, **kwargs):
        self.base_filename = filename
        self.process = None
        self.pid = None
        kwargs.update({'filename': filename})
        self.command = self.cmd % kwargs
        super(BackupRunner, self).__init__()

    @property
    def backup_type(self):
        return type(self).__name__

    def run(self):
        LOG.debug("BackupRunner running cmd: %s", self.command)
        self.process = subprocess.Popen(self.command, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        preexec_fn=os.setsid)
        self.pid = self.process.pid

    def __enter__(self):
        """Start up the process."""
        self._run_pre_backup()
        self.run()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Clean up everything."""
        if exc_type is not None:
            return False

        if hasattr(self, 'process'):
            try:
                # Send a sigterm to the session leader, so that all
                # child processes are killed and cleaned up on terminate
                # (Ensures zombie processes aren't left around on a FAILURE)
                # https://bugs.launchpad.net/trove/+bug/1253850
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.terminate()
            except OSError:
                # Already stopped
                pass
            utils.raise_if_process_errored(self.process, BackupError)
            if not self.check_process():
                raise BackupError

        self._run_post_backup()

        return True

    def metadata(self):
        """Hook for subclasses to store metadata from the backup."""
        return {}

    @property
    def filename(self):
        """Subclasses may overwrite this to declare a format (.tar)."""
        return self.base_filename

    @property
    def manifest(self):
        return "%s%s%s" % (self.filename,
                           self.zip_manifest,
                           self.encrypt_manifest)

    @property
    def zip_cmd(self):
        return ' | gzip' if self.is_zipped else ''

    @property
    def zip_manifest(self):
        return '.gz' if self.is_zipped else ''

    @property
    def encrypt_cmd(self):
        return (' | openssl enc -aes-256-cbc -salt -pass pass:%s' %
                self.encrypt_key) if self.is_encrypted else ''

    @property
    def encrypt_manifest(self):
        return '.enc' if self.is_encrypted else ''

    def check_process(self):
        """Hook for subclasses to check process for errors."""
        return True

    def read(self, chunk_size):
        return self.process.stdout.read(chunk_size)

    def _run_pre_backup(self):
        pass

    def _run_post_backup(self):
        pass
