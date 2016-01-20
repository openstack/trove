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

from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.couchdb import service
from trove.guestagent.strategies.restore import base


class CouchDBBackup(base.RestoreRunner):

    __strategy_name__ = 'couchdbbackup'
    base_restore_cmd = 'sudo tar xPf -'

    def __init__(self, *args, **kwargs):
        self.appStatus = service.CouchDBAppStatus()
        self.app = service.CouchDBApp(self.appStatus)
        super(CouchDBBackup, self).__init__(*args, **kwargs)

    def post_restore(self):
        """
        To restore from backup, all we need to do is untar the compressed
        database files into the database directory and change its ownership.
        """
        operating_system.chown(service.COUCHDB_LIB_DIR,
                               'couchdb',
                               'couchdb',
                               as_root=True)
        self.app.restart()
