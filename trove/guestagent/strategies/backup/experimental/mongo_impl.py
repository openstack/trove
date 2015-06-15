# Copyright (c) 2014 eBay Software Foundation
# Copyright 2015 Hewlett-Packard Development Company, L.P. and Tesora, Inc
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

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mongodb import (
    service as mongo_service)
from trove.guestagent.datastore.experimental.mongodb import (
    system as mongo_system)
from trove.guestagent.strategies.backup import base

CONF = cfg.CONF

LOG = logging.getLogger(__name__)
MONGODB_DBPATH = CONF.mongodb.mount_point
MONGO_DUMP_DIR = MONGODB_DBPATH + "/dump"
LARGE_TIMEOUT = 1200


class MongoDump(base.BackupRunner):
    """Implementation of Backup Strategy for MongoDump."""
    __strategy_name__ = 'mongodump'

    backup_cmd = 'mongodump --out ' + MONGO_DUMP_DIR

    def __init__(self, *args, **kwargs):
        self.app = mongo_service.MongoDBApp()
        super(MongoDump, self).__init__(*args, **kwargs)

    def _run_pre_backup(self):
        """Create archival contents in dump dir"""
        try:
            est_dump_size = self.estimate_dump_size()
            avail = operating_system.get_bytes_free_on_fs(MONGODB_DBPATH)
            if est_dump_size > avail:
                self.cleanup()
                # TODO(atomic77) Though we can fully recover from this error
                # BackupRunner will leave the trove instance in a BACKUP state
                raise OSError(_("Need more free space to run mongodump, "
                                "estimated %(est_dump_size)s"
                                " and found %(avail)s bytes free ") %
                              {'est_dump_size': est_dump_size,
                               'avail': avail})

            operating_system.create_directory(MONGO_DUMP_DIR, as_root=True)
            operating_system.chown(MONGO_DUMP_DIR, mongo_system.MONGO_USER,
                                   "nogroup", as_root=True)

            # high timeout here since mongodump can take a long time
            utils.execute_with_timeout(
                'mongodump', '--out', MONGO_DUMP_DIR,
                *(self.app.admin_cmd_auth_params()),
                run_as_root=True, root_helper='sudo',
                timeout=LARGE_TIMEOUT
            )
        except exception.ProcessExecutionError as e:
            LOG.debug("Caught exception when creating the dump")
            self.cleanup()
            raise e

    @property
    def cmd(self):
        """Tars and streams the dump dir contents to
        the stdout
        """
        cmd = 'sudo tar cPf - ' + MONGO_DUMP_DIR
        return cmd + self.zip_cmd + self.encrypt_cmd

    def cleanup(self):
        operating_system.remove(MONGO_DUMP_DIR, force=True, as_root=True)

    def _run_post_backup(self):
        self.cleanup()

    def estimate_dump_size(self):
        """
        Estimate the space that the mongodump will take based on the output of
        db.stats().dataSize. This seems to be conservative, as the actual bson
        output in many cases is a fair bit smaller.
        """
        dbs = self.app.list_all_dbs()
        # mongodump does not dump the content of the local database
        dbs.remove('local')
        dbstats = dict([(d, 0) for d in dbs])
        for d in dbstats:
            dbstats[d] = self.app.db_data_size(d)

        LOG.debug("Estimated size for databases: " + str(dbstats))
        return sum(dbstats.values())
