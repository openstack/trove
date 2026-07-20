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

from oslo_log import log as logging

import semantic_version
from trove.common import cfg
from trove.common import exception
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mysql import service
from trove.guestagent.datastore.mysql_common import manager
from trove.guestagent.datastore import service as base_service


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Manager(manager.MySqlManager):
    def __init__(self):
        status = base_service.BaseDbStatus(self.docker_client)
        app = service.MySqlApp(status, self.docker_client)
        adm = service.MySqlAdmin(app)

        super(Manager, self).__init__(app, status, adm)

    def pre_create_backup(self, context, **kwargs):
        LOG.info("Running pre_create_backup")
        status = {}
        try:
            INFO_FILE = "%s/xtrabackup_binlog_info" % self.app.get_data_dir()
            self.app.execute_sql("FLUSH TABLES WITH READ LOCK;")
            if self.app._is_mysql84():
                stt = self.app.execute_sql("SHOW BINARY LOG STATUS;")
            else:
                stt = self.app.execute_sql("SHOW MASTER STATUS;")
            for row in stt:
                status = {
                    'log_file': row._mapping['File'],
                    'log_position': row._mapping['Position'],
                    'log_executed_gtid_set': row._mapping['Executed_Gtid_Set'],
                }

                binlog = "\t".join(map(str, [
                    status['log_file'],
                    status['log_position'],
                    status['log_executed_gtid_set']]))
                operating_system.write_file(INFO_FILE, binlog, as_root=True)

            mount_point = CONF.get(CONF.datastore_manager).mount_point
            operating_system.sync(mount_point)
            operating_system.fsfreeze(mount_point)
        except Exception as e:
            LOG.error("Run pre_create_backup failed, error: %s", e)
            raise exception.BackupCreationError(str(e))

        return status

    def _get_default_tls_versions(self):
        # NOTE(mangust404): to operate correctly, your datastore version
        # should contain patch version number. Datastore name like "5.7"
        # wouldn't be able to use TLSv1.3
        mysql_5_7_0 = semantic_version.Version('5.7.0')
        mysql_5_7_27 = semantic_version.Version('5.7.27')

        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)

        if cur_ver < mysql_5_7_0:
            # For MySQL 5.6 there is no TLS support
            raise exception.BadRequest(
                'No support of TLS for MySQL prior to 5.7')
        elif cur_ver <= mysql_5_7_27:
            return 'TLSv1,TLSv1.1,TLSv1.2'
        elif cur_ver > mysql_5_7_27:
            return 'TLSv1.2,TLSv1.3'

    def _get_enable_client_ssl_overrides(self):
        mysql_8 = semantic_version.Version('8.0.0')
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        if cur_ver >= mysql_8:
            return {'ssl-mode': 'REQUIRED'}
        else:
            return {'ssl': 'on'}

    def _get_disable_client_ssl_overrides(self):
        mysql_8 = semantic_version.Version('8.0.0')
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        if cur_ver >= mysql_8:
            return {'ssl-mode': 'DISABLED'}
        else:
            return {'ssl': 'off'}

    def disable_ssl_certificate(self):
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        mysql_8_0 = semantic_version.Version('8.0.0')

        if cur_ver >= mysql_8_0:
            # Starting from MySQL 8.0 there is no reliable way to disable
            # SSL/TLS completely because caching_sha2_password depends on it
            raise exception.TroveError("Not supported for MySQL 8.0 and above")

        return super(Manager, self).disable_ssl_certificate()

    def _get_enable_ssl_overrides(self):
        files = self._get_ssl_files()
        overrides = {
            'ssl_cert': files['certificate'],
            'ssl_key': files['private_key'],
            'ssl_ca': files['ca'],
            'tls_version': self._get_default_tls_versions(),
            'require_secure_transport': 'ON'
        }
        return overrides

    def _get_disable_ssl_overrides(self):
        overrides = {
            'ssl_cert': '',
            'ssl_key': '',
            'ssl_ca': '',
            # The only reliable way to disable SSL is to unset tls_version.
            'tls_version': '',
            'require_secure_transport': 'OFF'
        }

        return overrides
