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
from trove.guestagent.strategy import Strategy
from trove.common import cfg
from trove.common import utils
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _  # noqa
from eventlet.green import subprocess

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CHUNK_SIZE = CONF.backup_chunk_size
BACKUP_USE_GZIP = CONF.backup_use_gzip_compression
BACKUP_USE_OPENSSL = CONF.backup_use_openssl_encryption
BACKUP_DECRYPT_KEY = CONF.backup_aes_cbc_key


class RestoreError(Exception):
    """Error running the Backup Command."""


class RestoreRunner(Strategy):
    """Base class for Restore Strategy implementations."""
    """Restore a database from a previous backup."""

    __strategy_type__ = 'restore_runner'
    __strategy_ns__ = 'trove.guestagent.strategies.restore'

    # The actual system calls to run the restore and prepare
    restore_cmd = None

    # The backup format type
    restore_type = None

    # Decryption Parameters
    is_zipped = BACKUP_USE_GZIP
    is_encrypted = BACKUP_USE_OPENSSL
    decrypt_key = BACKUP_DECRYPT_KEY

    def __init__(self, storage, **kwargs):
        self.storage = storage
        self.location = kwargs.pop('location')
        self.checksum = kwargs.pop('checksum')
        self.restore_location = kwargs.get('restore_location',
                                           '/var/lib/mysql')
        self.restore_cmd = (self.decrypt_cmd +
                            self.unzip_cmd +
                            (self.base_restore_cmd % kwargs))
        super(RestoreRunner, self).__init__()

    def pre_restore(self):
        """Hook that is called before the restore command."""
        pass

    def post_restore(self):
        """Hook that is called after the restore command."""
        pass

    def restore(self):
        self.pre_restore()
        content_length = self._run_restore()
        self.post_restore()
        return content_length

    def _run_restore(self):
        return self._unpack(self.location, self.checksum, self.restore_cmd)

    def _unpack(self, location, checksum, command):
        stream = self.storage.load(location, checksum)
        process = subprocess.Popen(command, shell=True,
                                   stdin=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        content_length = 0
        for chunk in stream:
            process.stdin.write(chunk)
            content_length += len(chunk)
        process.stdin.close()
        utils.raise_if_process_errored(process, RestoreError)
        LOG.debug("Restored %s bytes from stream." % content_length)

        return content_length

    @property
    def decrypt_cmd(self):
        if self.is_encrypted:
            return ('openssl enc -d -aes-256-cbc -salt -pass pass:%s | '
                    % self.decrypt_key)
        else:
            return ''

    @property
    def unzip_cmd(self):
        return 'gzip -d -c | ' if self.is_zipped else ''
