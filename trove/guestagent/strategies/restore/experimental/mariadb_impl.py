# Copyright 2016 Tesora Inc.
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

from trove.guestagent.datastore.experimental.mariadb.service import MariaDBApp
from trove.guestagent.datastore.mysql.service import MySqlAppStatus
from trove.guestagent.strategies.restore import mysql_impl


class MariaDBInnoBackupEx(mysql_impl.InnoBackupEx):

    def _build_app(self):
        return MariaDBApp(MySqlAppStatus.get())


class MariaDBInnoBackupExIncremental(MariaDBInnoBackupEx):
    pass
