# Copyright (c) 2014 eBay Software Foundation
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

import json

from oslo_log import log as logging

from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.couchbase import service
from trove.guestagent.datastore.experimental.couchbase import system
from trove.guestagent.strategies.backup import base


LOG = logging.getLogger(__name__)
OUTFILE = '/tmp' + system.BUCKETS_JSON


class CbBackup(base.BackupRunner):
    """
    Implementation of Backup Strategy for Couchbase.
    """
    __strategy_name__ = 'cbbackup'

    pre_backup_commands = [
        ['rm', '-rf', system.COUCHBASE_DUMP_DIR],
        ['mkdir', '-p', system.COUCHBASE_DUMP_DIR],
    ]

    post_backup_commands = [
        ['rm', '-rf', system.COUCHBASE_DUMP_DIR],
    ]

    @property
    def cmd(self):
        """
        Creates backup dump dir, tars it up, and encrypts it.
        """
        cmd = 'tar cpPf - ' + system.COUCHBASE_DUMP_DIR
        return cmd + self.zip_cmd + self.encrypt_cmd

    def _save_buckets_config(self, password):
        url = system.COUCHBASE_REST_API + '/pools/default/buckets'
        utils.execute_with_timeout('curl -u root:' + password +
                                   ' ' + url + ' > ' + OUTFILE,
                                   shell=True, timeout=300)

    def _backup(self, password):
        utils.execute_with_timeout('/opt/couchbase/bin/cbbackup',
                                   system.COUCHBASE_REST_API,
                                   system.COUCHBASE_DUMP_DIR,
                                   '-u', 'root', '-p', password,
                                   timeout=600, run_as_root=True,
                                   root_helper='sudo')

    def _run_pre_backup(self):
        try:
            for cmd in self.pre_backup_commands:
                utils.execute_with_timeout(*cmd)
            root = service.CouchbaseRootAccess()
            pw = root.get_password()
            self._save_buckets_config(pw)
            with open(OUTFILE, "r") as f:
                out = f.read()
                if out != "[]":
                    d = json.loads(out)
                    all_memcached = True
                    for i in range(len(d)):
                        bucket_type = d[i]["bucketType"]
                        if bucket_type != "memcached":
                            all_memcached = False
                            break
                    if not all_memcached:
                        self._backup(pw)
                    else:
                        LOG.info(_("All buckets are memcached.  "
                                   "Skipping backup."))
            operating_system.move(OUTFILE, system.COUCHBASE_DUMP_DIR)
            if pw != "password":
                # Not default password, backup generated root password
                operating_system.copy(system.pwd_file,
                                      system.COUCHBASE_DUMP_DIR,
                                      preserve=True, as_root=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error during pre-backup phase."))
            raise

    def _run_post_backup(self):
        try:
            for cmd in self.post_backup_commands:
                utils.execute_with_timeout(*cmd)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error during post-backup phase."))
            raise
