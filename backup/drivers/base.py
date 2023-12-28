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
import re
import signal
import subprocess

from oslo_config import cfg
from oslo_log import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseRunner(object):
    """Base class for Backup Strategy implementations."""

    # Subclass should provide the commands.
    cmd = ''
    restore_cmd = ''
    prepare_cmd = ''
    backup_log = ''

    encrypt_key = CONF.backup_encryption_key

    def __init__(self, *args, **kwargs):
        self.process = None
        self.pid = None
        self.base_filename = kwargs.get('filename')
        self.storage = kwargs.pop('storage', None)
        self.location = kwargs.pop('location', '')
        self.checksum = kwargs.pop('checksum', '')
        self._gzip = False

        if 'restore_location' not in kwargs:
            kwargs['restore_location'] = self.datadir
        self.restore_location = kwargs['restore_location']
        self.restore_content_length = 0

        self.command = self.cmd % kwargs

        if self.location.endswith('.enc') and not self.encrypt_key:
            raise Exception("Encryption key not provided with an encrypted "
                            "backup.")

        self.restore_command = ''
        # Only decrypt if the object name ends with .enc
        if self.location.endswith('.enc'):
            self.restore_command = self.decrypt_cmd
        self.restore_command = self.restore_cmd % kwargs
        self.prepare_command = self.prepare_cmd % kwargs

    @property
    def filename(self):
        """Subclasses may overwrite this to declare a format (.tar)."""
        return self.base_filename

    @property
    def manifest(self):
        """Target file name."""
        return "%s%s%s" % (self.filename,
                           self.zip_manifest,
                           self.encrypt_manifest)

    @property
    def zip_cmd(self):
        return self._gzip

    @property
    def unzip_cmd(self):
        return self._gzip

    @property
    def zip_manifest(self):
        return '.gz'

    @property
    def encrypt_cmd(self):
        """Encryption command.

        Since Victoria, trove no longer encrypts the backup data for the end
        user. This could be improved by giving users the capability to specify
        password when creating the backups.
        """
        return ""

    @property
    def decrypt_cmd(self):
        """Decryption command.

        Since Victoria, trove no longer encrypts the backup data for the end
        user. This command is only for backward compatibility.
        """
        if self.encrypt_key:
            return ('openssl enc -d -aes-256-cbc -md sha512 -pbkdf2 -iter '
                    '10000 -salt -pass pass:%s | '
                    % self.encrypt_key)
        else:
            return ''

    @property
    def encrypt_manifest(self):
        return '.enc' if self.encrypt_key else ''

    def _run(self):
        """Running backup cmd"""
        LOG.info("Running backup cmd: %s", self.command)
        with open(self.backup_log, "w+") as fp:
            if not self._gzip:
                self.process = subprocess.Popen(self.command.split(),
                                                shell=False,
                                                stdout=subprocess.PIPE,
                                                stderr=fp,
                                                preexec_fn=os.setsid)
            else:
                bkup_process = subprocess.Popen(self.command.split(),
                                                shell=False,
                                                stdout=subprocess.PIPE,
                                                stderr=fp)
                self.process = subprocess.Popen(["gzip"], shell=False,
                                                stdin=bkup_process.stdout,
                                                stdout=subprocess.PIPE,
                                                stderr=fp)
                bkup_process.stdout.close()
            self.pid = self.process.pid

    def __enter__(self):
        """Start up the process."""
        self.pre_backup()
        self._run()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Clean up everything."""
        if getattr(self, 'process', None):
            try:
                # Send a sigterm to the session leader, so that all
                # child processes are killed and cleaned up on terminate
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.terminate()
            except OSError:
                pass

            if exc_type is not None:
                return False

            if not self.check_process():
                with open(self.backup_log, "r") as fp:
                    err = fp.read()
                    if err:
                        raise Exception(err)
                raise Exception()

        self.post_backup()

        return True

    def read(self, chunk_size):
        return self.process.stdout.read(chunk_size)

    def get_metadata(self):
        """Hook for subclasses to get metadata from the backup."""
        return {}

    def check_process(self):
        """Hook for subclasses to check process for errors."""
        return True

    def check_restore_process(self):
        """Hook for subclasses to check the restore process for errors."""
        return True

    def pre_backup(self):
        """Hook for subclasses to run commands before backup."""
        pass

    def post_backup(self):
        """Hook for subclasses to run commands after backup."""
        pass

    def pre_restore(self):
        """Hook that is called before the restore command."""
        pass

    def post_restore(self):
        """Hook that is called after the restore command."""
        pass

    def unpack(self, location, checksum, command):
        stream = self.storage.load(location, checksum)

        LOG.info('Running restore from stream, command: %s', command)
        content_length = 0
        if not re.match(r'.*.gz', location) or not self._gzip:
            LOG.info('gz processor without gz file or with gzip disabled')
            self.process = subprocess.Popen(command.split(), shell=False,
                                            stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
            for chunk in stream:
                self.process.stdin.write(chunk)  # write data to mbstream
                content_length += len(chunk)
            stdout, stderr = self.process.communicate()
        else:
            LOG.info('gz processor with gz file')
            gunzip = subprocess.Popen(["gzip", "-d", "-c"], shell=False,
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
            self.process = subprocess.Popen(command.split(), shell=False,
                                            stdin=gunzip.stdout,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
            for chunk in stream:
                gunzip.stdin.write(chunk)  # write data to mbstream
                content_length += len(chunk)
            gunzip.stdin.close()
            gunzip.stdout.close()
            stdout, stderr = self.process.communicate()
        stdout_str = stdout.decode()
        stderr_str = stderr.decode()
        LOG.info("command: %s, stdout: %s, stderr: %s",
                 command, stdout_str, stderr_str)

        if not self.check_restore_process():
            LOG.info('self.check_restore_process() False')
            if stderr_str:
                raise Exception(stderr_str)
            raise Exception()

        return content_length

    def run_restore(self):
        return self.unpack(self.location, self.checksum, self.restore_command)

    def restore(self):
        """Restore backup to data directory.

        :returns Restored data size.
        """
        self.pre_restore()
        content_length = self.run_restore()
        self.post_restore()
        return content_length
