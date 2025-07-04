# Copyright 2020 Catalyst Cloud
# Copyright 2023 Bizfly Cloud
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
from oslo_log import log as logging
from oslo_utils.excutils import save_and_reraise_exception

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.utils import docker as docker_utils


from trove.guestagent.datastore.mariadb import service
from trove.guestagent.datastore.mysql_common import manager


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Manager(manager.MySqlManager):
    def __init__(self):
        status = service.MariadbAppStatus(self.docker_client)
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

    def pre_create_backup(self, context, **kwargs):
        LOG.info("Running pre_create_backup")
        status = {}
        try:
            INFO_FILE = "%s/xtrabackup_binlog_info" % self.app.get_data_dir()
            self.app.execute_sql("FLUSH TABLES WITH READ LOCK;")
            stt = self.app.execute_sql("SHOW MASTER STATUS;")
            for row in stt:
                status = {
                    'log_file': row._mapping['File'],
                    'log_position': row._mapping['Position']
                }

                for g in self.app.execute_sql(
                        "select @@global.gtid_current_pos;"):
                    gtid = g._mapping['@@global.gtid_current_pos']

                    status['log_executed_gtid_set'] = gtid

                binlog = "\t".join(map(str, [
                    status['log_file'],
                    status['log_position'],
                    status['log_executed_gtid_set']]))
                operating_system.write_file(INFO_FILE, binlog, as_root=True)

            mount_point = CONF.get(CONF.datastore_manager).mount_point
            operating_system.sync(mount_point)
            operating_system.fsfreeze(mount_point)
        except Exception as e:
            LOG.error("Run pre_create_backup failed, error: %s" % str(e))
            raise exception.BackupCreationError(str(e))
        return status

    def reset_password_for_restore(self, ds_version=None,
                                   data_dir='/var/lib/mysql/data'):
        """Reset the root password after restore the db data.

        uses --skip-grant-tables to temporarily disable auth and
        directly reset the root password via SQL.
        """
        LOG.info('Starting to reset password for restore')

        try:
            root_pass = self.app.get_auth_password(file="root.cnf")
        except exception.UnprocessableEntity:
            root_pass = utils.generate_random_password()
            self.app.save_password('root', root_pass)

        command = (
            f'--skip-grant-tables '
            f'--datadir={data_dir} '
        )
        reset_sql = (
            "FLUSH PRIVILEGES; "
            "ALTER USER 'root'@'localhost' IDENTIFIED BY '{}';"
        ).format(root_pass)
        reset_command = ["mariadb", "-u", "root", "-e", reset_sql]

        # Start the database container process.
        try:
            self.app.start_db(ds_version=ds_version, command=command)
            docker_utils.run_command(self.app.docker_client, reset_command)
        except Exception as err:
            with save_and_reraise_exception():
                LOG.error('Failed to reset password for restore, error: %s',
                          str(err))
        finally:
            try:
                LOG.debug(
                    'The init container log: %s',
                    docker_utils.get_container_logs(self.app.docker_client)
                )
                docker_utils.remove_container(self.app.docker_client)
            except Exception as err:
                LOG.error('Failed to remove container. error: %s',
                          str(err))
                pass
        LOG.info('Finished to reset password for restore')
