# Copyright 2016 IBM Corporation
#
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

from trove.guestagent.datastore.experimental.couchdb import service
from trove.guestagent.strategies.backup import base


class CouchDBBackup(base.BackupRunner):

    __strategy_name__ = 'couchdbbackup'

    @property
    def cmd(self):
        """
        CouchDB backup is based on a simple filesystem copy of the database
        files. Each database is a single fully contained append only file.
        For example, if a user creates a database 'foo', then a corresponding
        'foo.couch' file will be created in the database directory which by
        default is in '/var/lib/couchdb'.
        """
        cmd = 'sudo tar cpPf - ' + service.COUCHDB_LIB_DIR
        return cmd + self.zip_cmd + self.encrypt_cmd
