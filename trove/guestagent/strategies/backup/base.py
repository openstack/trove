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

import hashlib

from trove.guestagent.strategy import Strategy
from trove.openstack.common import log as logging
from trove.common import cfg, utils
from eventlet.green import subprocess

CONF = cfg.CONF

# Read in multiples of 128 bytes, since this is the size of an md5 digest block
# this allows us to update that while streaming the file.
#http://stackoverflow.com/questions/1131220/get-md5-hash-of-big-files-in-python
CHUNK_SIZE = CONF.backup_chunk_size
MAX_FILE_SIZE = CONF.backup_segment_max_size
BACKUP_CONTAINER = CONF.backup_swift_container
BACKUP_USE_GZIP = CONF.backup_use_gzip_compression
BACKUP_USE_OPENSSL = CONF.backup_use_openssl_encryption
BACKUP_ENCRYPT_KEY = CONF.backup_aes_cbc_key

LOG = logging.getLogger(__name__)


class BackupError(Exception):
    """Error running the Backup Command."""


class UnknownBackupType(Exception):
    """Unknown backup type"""


class BackupRunner(Strategy):
    """ Base class for Backup Strategy implementations """
    __strategy_type__ = 'backup_runner'
    __strategy_ns__ = 'trove.guestagent.strategies.backup'

    # The actual system call to run the backup
    cmd = None
    is_zipped = BACKUP_USE_GZIP
    is_encrypted = BACKUP_USE_OPENSSL
    encrypt_key = BACKUP_ENCRYPT_KEY

    def __init__(self, filename, **kwargs):
        self.filename = filename
        self.container = BACKUP_CONTAINER
        # how much we have written
        self.content_length = 0
        self.segment_length = 0
        self.process = None
        self.pid = None
        self.writer = None
        self.file_number = 0
        self.written = -1
        self.end_of_file = False
        self.end_of_segment = False
        self.file_checksum = hashlib.md5()
        self.segment_checksum = hashlib.md5()
        self.command = self.cmd % kwargs
        super(BackupRunner, self).__init__()

    @property
    def backup_type(self):
        return type(self).__name__

    def run(self):
        self.process = subprocess.Popen(self.command, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        self.pid = self.process.pid

    def __enter__(self):
        """Start up the process"""
        self.run()
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
            utils.raise_if_process_errored(self.process, BackupError)
            if not self.check_process():
                raise BackupError

        return True

    @property
    def segment(self):
        return '%s_%08d' % (self.filename, self.file_number)

    @property
    def manifest(self):
        """Subclasses may overwrite this to declare a format (.gz, .tar)"""
        return self.filename

    @property
    def prefix(self):
        return '%s/%s_' % (self.container, self.filename)

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
        """Wrap self.process.stdout.read to allow for segmentation."""
        if self.end_of_segment:
            self.segment_length = 0
            self.segment_checksum = hashlib.md5()
            self.end_of_segment = False

        # Upload to a new file if we are starting or too large
        if self.segment_length > (MAX_FILE_SIZE - CHUNK_SIZE):
            self.file_number += 1
            self.end_of_segment = True
            return ''

        chunk = self.process.stdout.read(CHUNK_SIZE)
        if not chunk:
            self.end_of_file = True
            return ''

        self.file_checksum.update(chunk)
        self.segment_checksum.update(chunk)
        self.content_length += len(chunk)
        self.segment_length += len(chunk)
        return chunk
