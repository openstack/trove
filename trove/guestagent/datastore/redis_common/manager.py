# Copyright 2026 PS Cloud Services
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
from trove.common import cfg
from trove.common import exception
from trove.common.notification import EndNotification
from trove.common import ssl
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import manager
from trove.guestagent.datastore import service as base_service

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
OSADMIN_USER = 'os_admin'
REPLICATION_USER = 'replicator'


class RedisManager(manager.Manager):
    DATASTORE_NAME = None
    APP_CLASS = None

    def __init__(self):
        if self.DATASTORE_NAME is None:
            raise NotImplementedError(
                "DATASTORE_NAME must be defined by the datastore manager")

        if self.APP_CLASS is None:
            raise exception.TroveError(
                f"{self.__class__.__name__} must define APP_CLASS"
            )

        super().__init__(self.DATASTORE_NAME)
        self.status = base_service.BaseDbStatus(self.docker_client)
        self.app = self.APP_CLASS(self.status, self.docker_client)
        self.adm = self.app.adm

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot, ds_version=None):
        operating_system.ensure_directory(self.app.datadir,
                                          user=self.app.database_service_uid,
                                          group=self.app.database_service_gid,
                                          force=True, as_root=True)

        LOG.info("Preparing database config files")
        self.configuration_manager.reset_configuration(config_contents)
        self.update_overrides(context, overrides)

        # Restore data from backup
        if backup_info:
            self.perform_restore(context, self.app.datadir, backup_info)

        if not operating_system.exists(self.app.ACL_FILE, as_root=True):

            osadmin_password = self.app.get_osadmin_password()

            # Enable ping without auth for docker health checks
            # And also full access account for admin purposes.
            acl_rules = (
                "user default on nopass ~* &* -@all +ping\n"
                f"user {OSADMIN_USER} on >{osadmin_password} ~* &* +@all\n"
            )

            operating_system.write_file(
                self.app.ACL_FILE,
                acl_rules,
                as_root=True
            )
            operating_system.chown(self.app.ACL_FILE,
                                   self.app.database_service_uid,
                                   self.app.database_service_gid,
                                   force=True, as_root=True)

        self.app.enable_aclfile()

        if snapshot:
            # This instance is a replica
            self.attach_replica(context, snapshot, snapshot['config'])

        self.app.start_db(ds_version=ds_version, memory_mb=memory_mb)

    def enable_root(self, context):
        root_password = self.app.set_password()
        root = self.adm.enable_root(root_password)
        return root

    def enable_root_with_password(self, context, root_password=None):
        self.app.set_password(root_password)
        root = self.adm.enable_root(root_password)
        return root

    def apply_overrides(self, context, overrides):
        """Reload config."""
        LOG.info("Reloading database config.")
        self.app.apply_overrides(overrides)
        LOG.info("Finished reloading database config.")

    def create_backup(self, context, backup_info):
        """Create backup for the database.

        :param context: User context object.
        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """
        LOG.info("Creating backup %s", backup_info['id'])
        with EndNotification(context):
            volumes_mapping = {}
            volumes_mapping[self.app.datadir] = {
                'bind': ('/var/lib/%s' % self.DATASTORE_NAME),
                'mode': 'rw'
            }
            extra_params = ""

            self.adm.database_sync()

            self.app.create_backup(context, backup_info,
                                   volumes_mapping=volumes_mapping,
                                   need_dbuser=False,
                                   extra_params=extra_params)

    def attach_replica(self, context, replica_info, slave_config,
                       restart=False):
        LOG.debug("attach_replica")
        self.replication.enable_as_slave(
            self.app,
            replica_info, None)  # type: ignore

        if "cert_container" in replica_info:
            self.enable_ssl_certificate(
                replica_info["ssl_mode"], replica_info["cert_container"],
                apply_overrides=True, is_startup=True)

        if restart:
            self.app.restart()

    def make_read_only(self, context, read_only):
        # there is no way to mark redis instance
        # readonly except making it slave
        pass

    def get_latest_txn_id(self, context):
        # No transactions support in Redis
        pass

    def wait_for_txn(self, context, txn):
        # No transactions support in Redis
        pass

    def upgrade(self, context, upgrade_info):
        """Upgrade the database."""
        LOG.info("Starting to upgrade database, upgrade_info: %s",
                 upgrade_info)
        self.app.upgrade(upgrade_info)

    def rebuild(self, context, ds_version, config_contents=None,
                config_overrides=None):
        """Restore datastore service after instance rebuild."""
        LOG.info("Starting to restore database service")
        self.status.begin_install()

        operating_system.ensure_directory(self.app.datadir,
                                          user=self.app.database_service_uid,
                                          group=self.app.database_service_gid,
                                          force=True, as_root=True)
        try:
            # Prepare configuration
            LOG.debug("Preparing database configuration")
            self.app.configuration_manager.reset_configuration(config_contents)

            self.app.update_overrides(config_overrides)

            # Enable SSL, if necessary
            if self.ssl_mode_at_least(CONF.ssl_mode, ssl.MODE_BASIC):
                cert_container = self._read_ssl_files()
                self.enable_ssl_certificate(
                    CONF.ssl_mode, cert_container,
                    apply_overrides=True, is_startup=True)

            self.app.enable_aclfile()

            # Start database service.
            self.app.start_db(ds_version=ds_version)
        except Exception as e:
            LOG.error("Failed to restore database service after rebuild, "
                      "error: %s", e)
            self.prepare_error = True
            raise
        finally:
            self.status.end_install(error_occurred=self.prepare_error)

    def pre_create_backup(self, context, **kwargs):
        LOG.info("Running pre_create_backup")
        status = {}
        try:
            self.adm.database_sync()
            mount_point = CONF.get(CONF.datastore_manager).mount_point
            # Sync Disk
            operating_system.sync(mount_point)
            # Freeze FS
            operating_system.fsfreeze(mount_point)
        except Exception as e:
            LOG.error("Run pre_create_backup failed, error: %s", e)
            raise exception.BackupCreationError(str(e))

        return status

    def _get_ssl_files(self):
        return {
            "private_key": f"{self.app.datadir}/server.key",
            "certificate": f"{self.app.datadir}/server.crt",
            "ca": f"{self.app.datadir}/ca.crt"
        }

    def _enable_ssl_certificate_impl(self, mode, apply_overrides=True):
        LOG.debug("Enable SSL mode: %s", mode)

        overrides = {
            "tls-ca-cert-file": "ca.crt",
            "tls-cert-file": "server.crt",
            "tls-key-file": "server.key"
        }
        if self.ssl_mode_at_least(mode, ssl.MODE_MTLS):
            overrides["port"] = 0
            overrides["tls-port"] = 6379
            overrides["tls-auth-clients"] = "yes"
            overrides["tls-replication"] = "yes"
        elif self.ssl_mode_at_least(mode, ssl.MODE_ENFORCED):
            overrides["port"] = 0
            overrides["tls-port"] = 6379
            overrides["tls-auth-clients"] = "no"
            overrides["tls-replication"] = "yes"
        elif self.ssl_mode_at_least(mode, ssl.MODE_BASIC):
            overrides["port"] = 6379
            overrides["tls-port"] = 6380
            overrides["tls-auth-clients"] = "no"

        if apply_overrides:
            self.app.update_overrides(overrides)
        return True

    def _disable_ssl_certificate_impl(self, apply_overrides=True):
        LOG.debug("Disable SSL")

        overrides = {
            "port": 6379,
            "tls-port": 0,
            "tls-auth-clients": "no"
        }

        if apply_overrides:
            self.app.update_overrides(overrides)
        return True

    def show_ssl_status(self):
        tls_port = self.configuration_manager.get_value("tls-port")
        if tls_port and tls_port[0] and tls_port[0][0] > 0:
            certificate = operating_system.read_file(
                f"{self.app.datadir}/server.crt", as_root=True)
            return {"certificate": certificate, "status": "on"}
        else:
            return {"status": "off"}
