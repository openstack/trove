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
import semantic_version

from trove.common import cfg
from trove.guestagent.datastore.mysql import service
from trove.guestagent.datastore.mysql_common import manager

CONF = cfg.CONF


class Manager(manager.MySqlManager):
    def __init__(self):
        status = service.MySqlAppStatus(self.docker_client)
        app = service.MySqlApp(status, self.docker_client)
        adm = service.MySqlAdmin(app)

        super(Manager, self).__init__(app, status, adm)

    def get_start_db_params(self, data_dir):
        """Get parameters for starting database.

        Cinder volume initialization(after formatted) may leave a lost+found
        folder.

        The --ignore-db-dir option is deprecated in MySQL 5.7. With the
        introduction of the data dictionary in MySQL 8.0, it became
        superfluous and was removed in that version.
        """
        params = f'--datadir={data_dir}'

        mysql_8 = semantic_version.Version('8.0.0')
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        params = f'--datadir={data_dir}'
        if cur_ver < mysql_8:
            params = (f"{params} --ignore-db-dir=lost+found "
                      f"--ignore-db-dir=conf.d")

        return params
