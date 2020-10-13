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
from trove.guestagent.datastore.mariadb import service
from trove.guestagent.datastore.mysql_common import manager
from trove.guestagent.datastore.mysql_common import service as mysql_service


class Manager(manager.MySqlManager):
    def __init__(self):
        status = mysql_service.BaseMySqlAppStatus(self.docker_client)
        app = service.MariaDBApp(status, self.docker_client)
        adm = service.MariaDBAdmin(app)

        super(Manager, self).__init__(app, status, adm)

    def get_start_db_params(self, data_dir):
        """Get parameters for starting database.

        Cinder volume initialization(after formatted) may leave a lost+found
        folder.
        """
        return (f'--ignore-db-dir=lost+found --ignore-db-dir=conf.d '
                f'--datadir={data_dir}')
