# Copyright (c) 2013 OpenStack Foundation
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

import re

from eventlet.green import subprocess

from trove.common import exception
from trove.guestagent.strategies.restore import base
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class PgDump(base.RestoreRunner):
    """Implementation of Restore Strategy for pg_dump."""
    __strategy_name__ = 'pg_dump'
    base_restore_cmd = 'sudo -u postgres psql '

    IGNORED_ERROR_PATTERNS = [
        re.compile("ERROR:\s*role \"postgres\" already exists"),
    ]

    def restore(self):
        """We are overriding the base class behavior
        to perform custom error handling.
        """
        self.pre_restore()
        content_length = self._execute_postgres_restore()
        self.post_restore()
        return content_length

    def _execute_postgres_restore(self):
        # Postgresql outputs few benign messages into the stderr stream
        # during a normal restore procedure.
        # We need to watch for those and avoid raising
        # an exception in response.
        # Message 'ERROR:  role "postgres" already exists'
        # is expected and does not pose any problems to the restore operation.

        stream = self.storage.load(self.location, self.checksum)
        process = subprocess.Popen(self.restore_cmd, shell=True,
                                   stdin=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        content_length = 0
        for chunk in stream:
            process.stdin.write(chunk)
            content_length += len(chunk)
        process.stdin.close()
        self._handle_errors(process)
        LOG.debug("Restored %s bytes from stream." % content_length)

        return content_length

    def _handle_errors(self, process):
        # Handle messages in the error stream of a given process.
        # Raise an exception if the stream is not empty and
        # does not match the expected message sequence.

        try:
            err = process.stderr.read()
            # Empty error stream is always accepted as valid
            # for future compatibility.
            if err:
                for message in err.splitlines(False):
                    if not any(regex.match(message)
                               for regex in self.IGNORED_ERROR_PATTERNS):
                        raise exception(message)
        except OSError:
            pass
