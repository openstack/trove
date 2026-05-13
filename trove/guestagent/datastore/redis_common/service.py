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

import docker
import os
from oslo_log import log as logging
from valkey.exceptions import ConnectionError
from valkey import Valkey
from trove.common import cfg, constants, exception, stream_codecs, utils
from trove.common.db.redis_common import models
from trove.guestagent.common import configuration, guestagent_utils, \
    operating_system
from trove.guestagent.datastore.redis_common import manager
from trove.guestagent.datastore import service
from trove.guestagent.utils import docker as docker_util
from trove.instance import service_status
from typing import Union, List

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CNF_EXT = 'conf'


class RedisApp(service.BaseDbApp):
    DATASTORE_NAME = 'redis'
    CLI_BINARY = 'redis-cli'
    CONFIG_FILE = '/etc/redis/redis.conf'
    CNF_INCLUDE_DIR = '/etc/redis/conf.d'
    SOCKET_PATH = '/var/lib/redis-socket'
    CONTAINER_SOCKET = '/var/run/redis/redis.sock'
    # ACL file should persist after rebuilds.
    # Store it in the data config directory.
    ACL_FILE = '/var/lib/redis/conf.d/users.acl'
    SERVER_BINARY = 'redis-server'
    DATA_ENV_NAME = 'REDIS_DATA'
    _configuration_manager = None

    HEALTHCHECK = {
        "test": [
            "CMD-SHELL",
            f"redis-cli -s {CONTAINER_SOCKET} ping | grep -qx PONG"],
        "start_period": 10 * 1000000000,  # 10 seconds in nanoseconds
        "interval": 10 * 1000000000,
        "timeout": 5 * 1000000000,
        "retries": 3
    }

    @property
    def configuration_manager(self):
        if self._configuration_manager:
            return self._configuration_manager

        config_manager = configuration.ConfigurationManager
        config_value_mappings = {'yes': True, 'no': False, "''": None}
        self._value_converter = stream_codecs.StringConverter(
            config_value_mappings)
        self._configuration_manager = config_manager(
            self.CONFIG_FILE,
            self.database_service_uid,
            self.database_service_gid,
            stream_codecs.PropertiesCodec(
                unpack_singletons=False,
                string_mappings=config_value_mappings),
            requires_root=True,
            override_strategy=configuration.IndexOverrideStrategy(
                self.CNF_INCLUDE_DIR, CNF_EXT),
        )
        return self._configuration_manager

    def __init__(self, status, docker_client):
        super(RedisApp, self).__init__(status, docker_client)

        mount_point = cfg.get_configuration_property('mount_point')
        self.datadir = mount_point
        self.adm = self.build_admin_client()

    def set_password(self, password=None):
        if password is None:
            password = utils.generate_random_password()
        self.save_password('root', password)
        return password

    @classmethod
    def get_password(cls):
        try:
            return cls.get_auth_password(file="default.cnf")
        except (exception.UnprocessableEntity, KeyError):
            return None

    @classmethod
    def get_osadmin_password(cls):
        try:
            return cls.get_auth_password(file="osadmin.cnf")
        except (exception.UnprocessableEntity, KeyError) as e:
            LOG.info("creating new osadmin password: %s", e)
            return cls.create_osadmin_password()

    @classmethod
    def create_osadmin_password(cls, password=None):
        if password is None:
            password = utils.generate_random_password()
        cls.save_password('osadmin', password)
        return password

    # Returns replication password
    def get_masterauth(self):
        try:
            return self.get_auth_password(file="masterauth.cnf")
        except exception.UnprocessableEntity:
            return self.set_masterauth(None)

    def reload(self):
        docker_util.restart_container(self.docker_client)

    def update_overrides(self, overrides):
        """Update config options in the include directory."""
        if overrides:
            self.configuration_manager.apply_user_override(overrides)

    def apply_overrides(self, overrides):
        """Reload config."""
        docker_util.restart_container(self.docker_client)

    def get_port(self):
        try:
            port = self.get_configuration_property('port')
        except Exception:
            port = 6379
        return port

    def build_admin_client(self):
        socket = f"{self.SOCKET_PATH}/{self.DATASTORE_NAME}.sock"
        password = self.get_osadmin_password()
        LOG.info('Create build_admin_client %s', socket)
        return RedisAdmin(
            unix_socket_path=socket,
            username=manager.OSADMIN_USER,
            password=password)

    def get_configuration_property(self, name, default=None):
        """Return the value of a Redis configuration property.
        Returns a single value for single-argument properties or
        a list otherwise.
        """
        return utils.unpack_singleton(
            self.configuration_manager.get_value(name, default))

    def get_config_command_name(self):
        """Get current name of the 'CONFIG' command.
        """
        renamed_cmds = self.configuration_manager.get_value('rename-command')
        if renamed_cmds:
            for name_pair in renamed_cmds:
                if name_pair[0] == 'CONFIG':
                    return name_pair[1]

        return None

    def start_db(self, update_db=False, ds_version=None, command=None,
                 extra_volumes=None, memory_mb=None):
        """Start and wait for database service."""
        docker_image = CONF.get(CONF.datastore_manager).docker_image
        image = (f'{docker_image}:latest' if not ds_version else
                 f'{docker_image}:{ds_version}')

        if not command:
            command = f'{self.SERVER_BINARY} {self.CONFIG_FILE}'

        for folder in [f"/etc/{self.DATASTORE_NAME}",
                       self.SOCKET_PATH]:
            operating_system.ensure_directory(
                folder, user=self.database_service_uid,
                group=self.database_service_gid, force=True,
                as_root=True)

        volumes = {
            f'/etc/{self.DATASTORE_NAME}': {
                'bind': f'/etc/{self.DATASTORE_NAME}', 'mode': 'rw'},
            self.datadir: {'bind': self.datadir, 'mode': 'rw'},
            self.SOCKET_PATH: {
                'bind': f'/var/run/{self.DATASTORE_NAME}', 'mode': 'rw'}
        }

        if extra_volumes:
            volumes.update(extra_volumes)

        ports = {}
        cfg_ports = cfg.get_configuration_property('tcp_ports')
        tcp_ports: List[List[Union[int, str]]] = cfg_ports  # type: ignore
        for port_range in tcp_ports:
            for port in port_range:
                ports[f'{port}/tcp'] = port

        if CONF.network_isolation and \
                os.path.exists(constants.ETH1_CONFIG_PATH):
            network_mode = constants.DOCKER_HOST_NIC_MODE
        else:
            network_mode = constants.DOCKER_BRIDGE_MODE

        user = "%s:%s" % (self.database_service_uid, self.database_service_gid)
        try:
            environment = {}
            environment[self.DATA_ENV_NAME] = self.datadir

            docker_util.start_container(
                self.docker_client,
                image,
                volumes=volumes,
                network_mode=network_mode,
                ports=ports,
                user=user,
                environment=environment,
                healthcheck=self.HEALTHCHECK,
                command=command
            )
        except Exception:
            LOG.exception("Failed to start database service")
            raise exception.TroveError("Failed to start database service")

        if not self.status.wait_for_status(
            service_status.ServiceStatuses.HEALTHY,
            CONF.state_change_wait_time, update_db
        ):
            raise exception.TroveError("Failed to start database service")

    def restart(self):
        LOG.info("Restarting database")

        try:
            docker_util.restart_container(self.docker_client)
        except Exception:
            LOG.exception("Failed to restart database")
            raise exception.TroveError("Failed to restart database")

        if not self.status.wait_for_status(
            service_status.ServiceStatuses.HEALTHY,
            CONF.state_change_wait_time, update_db=True
        ):
            raise exception.TroveError("Failed to start database")

        LOG.info("Finished restarting database")

    def restore_backup(self, context, backup_info, restore_location):
        backup_id = backup_info['id']
        storage_driver = CONF.storage_strategy
        backup_driver = self.get_backup_strategy()
        user_token = context.auth_token
        swift_url = backup_info.get('swift_url')
        if not swift_url:
            raise exception.TroveError(
                "Missing swift_url in backup metadata.")
        image = self.get_backup_image()
        name = 'db_restore'
        volumes = {
            self.datadir: {
                'bind': self.datadir,
                'mode': 'rw'
            }
        }

        command = (
            f'python3 main.py --nobackup '
            f'--storage-driver={storage_driver} --driver={backup_driver} '
            f'--os-token={user_token} --swift-url={swift_url} '
            f'--restore-from={backup_info["location"]} '
            f'--restore-checksum={backup_info["checksum"]} '
        )
        if CONF.swift_api_insecure:
            command = (f"{command} --swift-api-insecure")
        if CONF.backup_aes_cbc_key:
            command = (f"{command} "
                       f"--backup-encryption-key={CONF.backup_aes_cbc_key}")

        LOG.debug('Stop the database and clean up the data before restore '
                  'from %s', backup_id)
        self.stop_db()
        operating_system.remove_dir_contents(self.datadir)

        # Start to run restore inside a separate docker container
        LOG.info('Starting to restore backup %s, command: %s', backup_id,
                 command)
        output, ret = docker_util.run_container(
            self.docker_client, image, name,
            volumes=volumes, command=command)
        result = output[-1]
        if not ret:
            msg = f'Failed to run restore container, error: {result}'
            LOG.error(msg)
            raise Exception(msg)

        operating_system.chown(self.datadir, self.database_service_uid,
                               self.database_service_gid, force=True,
                               as_root=True)

        # Use osadmin password from restored backup
        self.adm.set_osadmin_password(self.get_osadmin_password())

    def enable_aclfile(self):
        self.configuration_manager.apply_system_override({
            'aclfile': self.ACL_FILE})

    # Enables replication password (mastearauth conf)
    def set_masterauth(self, password=None):
        if password is None:
            password = utils.generate_random_password()
        self.save_password('masterauth', password)
        self.configuration_manager.apply_system_override(
            {'masterauth': password})
        self.adm.create_replication_user(
            models.RedisCommonUser(
                name=manager.REPLICATION_USER, password=password))
        return password

    def upgrade(self, upgrade_info):
        """Upgrade the database."""
        new_version = upgrade_info.get('datastore_version')

        LOG.info('Stopping db container for upgrade')
        self.stop_db()

        LOG.info('Deleting db container for upgrade')
        docker_util.remove_container(self.docker_client)

        LOG.info('Remove unused images before starting new db container')
        docker_util.prune_images(self.docker_client)

        LOG.info('Starting new db container with version %s for upgrade',
                 new_version)
        self.start_db(update_db=True, ds_version=new_version)

    def is_replica(self):
        try:
            role = self.adm.connection.info('replication').get('role')
            return role == 'slave' or role == 'replica'
        except Exception:
            return False

    def stop_db(self, update_db=False):
        LOG.info("Stopping database gracefully.")
        try:
            container = self.docker_client.containers.get("database")
        except docker.errors.NotFound:
            return
        original_rp = container.attrs["HostConfig"]["RestartPolicy"]
        try:
            # Prevent Docker from restarting the container after Redis exits.
            LOG.debug("Restart policy: %r", original_rp)
            container.update(
                restart_policy={"Name": "no", "MaximumRetryCount": 0})

            try:
                self.adm.connection.shutdown(save=True)
            except ConnectionError:
                # Expected: SHUTDOWN closes the client connection because
                # the Redis server exits.
                pass

            if not self.status.wait_for_status(
                service_status.ServiceStatuses.SHUTDOWN,
                CONF.state_change_wait_time,
                update_db
            ):
                raise exception.TroveError("Failed to stop database")

        finally:
            # Restore the normal policy for future Docker/host restarts.
            container.update(restart_policy=original_rp)

        os.sync()


class RedisAdmin(object):
    ROOT_USERNAME = 'root'

    def __init__(self, unix_socket_path=None, username=None, password=None):
        self._connection = None
        self._unix_socket_path = unix_socket_path
        self._username = username
        self._password = password

    def connect(self):
        self._connection = Valkey(
            unix_socket_path=self._unix_socket_path,
            username=self._username,
            password=self._password)

    def set_osadmin_password(self, password):
        self._password = password
        self.connect()

    @property
    def connection(self):
        if not self._connection:
            self.connect()
        return self._connection

    def build_root_user(self, password=None):
        return models.RedisCommonUser.root(
            name=self.ROOT_USERNAME, password=password)

    def enable_root(self, root_password=None):
        """Create a superuser user or reset the superuser password."""
        root = self.build_root_user(root_password)
        self.create_root_user(root, reset_passwords=True)

        return root.serialize()

    def disable_root(self):
        self.connection.acl_setuser(
            username=self.ROOT_USERNAME,
            enabled=False,
        )
        self.connection.acl_save()

    def is_root_enabled(self):
        user_acl = self.connection.acl_getuser(self.ROOT_USERNAME)

        if not user_acl:
            # Root user doesn't exists
            return False

        flags = user_acl.get("flags", [])

        if isinstance(flags, str):
            flags = flags.split()

        # Check that root user is enabled
        return "on" in flags

    def _validate_categories(self, requested_categories):
        requested_categories = set(requested_categories)
        available_categories = set(self.connection.acl_cat() + ['all'])

        valid_categories = requested_categories & available_categories
        invalid_categories = requested_categories - available_categories

        if invalid_categories:
            raise exception.TroveError(
                "ACL category doesn't exists: %s\n"
                "Available categories: %s" %
                (
                    ", ".join(sorted(invalid_categories)),
                    ", ".join(sorted(available_categories))
                )
            )

        return valid_categories

    def grant_access(self, username, hostname, databases):
        # hostname is not applicable to Redis ACLs
        requested_categories = set(databases)
        valid_categories = self._validate_categories(requested_categories)
        LOG.debug(
            'Grant access, requested_categories = %s, valid categories = %s',
            requested_categories, valid_categories)

        if valid_categories:
            self.connection.acl_setuser(
                username=username,
                enabled=True,
                categories=[
                    f"+@{category}"
                    for category in sorted(valid_categories)
                ],
            )
            self.connection.acl_save()

    def revoke_access(self, username, hostname, database):
        # hostname is not applicable to Redis ACLs
        available_categories = set(self.connection.acl_cat())

        if database not in available_categories:
            LOG.warning(
                ("ACL category %s is not available, "
                 "skipping revoke for user %s"),
                database,
                username,
            )
            return
        self.connection.acl_setuser(
            username=username,
            enabled=True,
            categories=[f"-@{database}"],
        )
        self.connection.acl_save()

    def list_access(self, username, hostname):
        # hostname is not applicable to Redis ACLs
        access = [
            {'_name': db[2:], '_collate': '', '_character_set': ''}
            for db in self._get_user_categories(username)
            if db.startswith("+@")]
        return access

    def create_databases(self, *args, **kwargs):
        raise exception.TroveError("Creating databases is not supported")

    def create_database(self, *args, **kwargs):
        raise exception.TroveError("Creating database is not supported")

    def delete_database(self, database):
        raise exception.TroveError("Deleting database is not supported")

    def list_databases(self, limit=None, marker=None, include_marker=False):
        dbs = [
            models.RedisCommonSchema(name=db)
            for db in self.connection.acl_cat()
        ]
        return guestagent_utils.serialize_list(
            dbs,
            limit=limit, marker=marker, include_marker=include_marker)

    def create_users(self, users):
        for user in users:
            self.create_non_root_user(
                models.RedisCommonUser.deserialize(user, False)
            )

    def create_user(self, user, enabled=True, **kwargs):
        LOG.info(f"Create user {user.name}")
        if not user.password:
            kwargs["nopass"] = True
        else:
            kwargs["passwords"] = [f"+{user.password}"]
        if "categories" in kwargs:
            kwargs["categories"] = kwargs["categories"]
        if user.databases:
            requested_categories = [db["_name"] for db in user.databases]
            valid_categories = self._validate_categories(requested_categories)
            LOG.debug(
                'Grant access on creation, requested_categories = %s',
                requested_categories)

            categories = [f"+@{db}" for db in valid_categories]
            if categories:
                if "categories" not in kwargs:
                    kwargs["categories"] = []
                kwargs["categories"].extend(categories)
                # Remove duplicates
                kwargs["categories"] = list(
                    dict.fromkeys(kwargs["categories"]))

        self.connection.acl_setuser(user.name,
                                    enabled=enabled, **kwargs)
        self.connection.acl_save()

    def create_root_user(self, user, **kwargs):
        self.create_user(user, categories=["+@all"], channels=["*"],
                         keys=["~*"], **kwargs)

    def create_replication_user(self, user, **kwargs):
        self.create_user(user, commands=["+psync", "+replconf", "+ping"],
                         channels=["*"], keys=["~*"], **kwargs)

    def create_non_root_user(self, user, **kwargs):
        if user.name in self.ignore_users:
            raise exception.TroveError("%s username is reserved" % user.name)

        self.create_user(
            user,
            categories=CONF.get(CONF.datastore_manager).user_acl_categories,
            keys=["~*"], channels=["*"], **kwargs)

    def list_users(self, limit=None, marker=None, include_marker=False):
        """List all users on the instance along with their access permissions.
        Return a paginated list of serialized Redis users.
        """
        return guestagent_utils.serialize_list(
            self._get_users(),
            limit=limit, marker=marker, include_marker=include_marker)

    def _get_users(self):
        """Return all non-system Redis users on the instance."""
        results = self.connection.acl_list()

        names = {acl_info.split(" ")[1] for acl_info in results}
        return [
            self._build_user(name, show_full_acl=True)
            for name in sorted(names)
            if name not in self.ignore_users
        ]

    def _build_user(self, username, show_full_acl=False):
        """Build a model representation of a Redis user."""
        if username == self.ROOT_USERNAME:
            return self.build_root_user()
        if show_full_acl:
            databases = self._get_user_categories(username)
        else:
            databases = [
                db[2:]
                for db in self._get_user_categories(username)
                if db[:1] != '-'
            ]
        return models.RedisCommonUser(username, databases=databases)

    def delete_user(self, user):
        """Delete the specified user."""
        if not isinstance(user, models.RedisCommonUser):
            user = models.RedisCommonUser.deserialize(user, False)
        user.check_delete()
        if user.name:
            self.connection.acl_deluser(user.name)
            self.connection.acl_save()

    def get_user(self, username, hostname):
        """Return a serialized representation of a user with a given name."""
        user = self._find_user(username)
        return user.serialize() if user is not None else None

    def _find_user(self, username):
        """Lookup a user with a given username.

        Return a new Redis user instance or None if no match is found.
        """
        for acl_info in self.connection.acl_list():  # type: ignore
            name = acl_info.split(" ")[1]
            if name == username:
                return self._build_user(username)
        return None

    # Return ACL categories as databases
    def _get_user_categories(self, username):
        user_acl = self.connection.acl_getuser(username)
        if not user_acl or 'categories' not in user_acl:
            return []

        return user_acl["categories"]

    def user_exists(self, username):
        """Return whether a given user exists on the instance."""
        results = self._find_user(username)

        return bool(results)

    def update_attributes(self, username, hostname, user_attrs):
        """Change the attributes of an existing user."""
        LOG.debug("Changing user attributes for user %s.", username)

        user = self._find_user(username)
        if not user:
            return

        is_changed = False

        new_password = user_attrs.get('password')
        if new_password:
            LOG.debug("Password changed for user %s.", username)
            user.password = new_password
            is_changed = True

        if 'name' in user_attrs and user_attrs['name'] != username:
            new_name = user_attrs.get('name')
            if new_name in self.ignore_users:
                raise exception.TroveError(
                    "%s username is reserved" % new_name)
            LOG.debug(
                "Name changed for user %s, new name: %s.", username, new_name)
            self.delete_user(user)
            user.name = new_name
            is_changed = True

        if is_changed:
            self.create_non_root_user(user, reset_passwords=True)

    def change_passwords(self, users):
        """Change the passwords of one or more existing users.

        The users parameter is a list of serialized Redis users.
        """
        for user in users:
            user_dict = {
                '_name': user['name'],
                '_host': user['host'],
                '_password': user['password']}
            self.create_non_root_user(
                models.RedisCommonUser.deserialize(user_dict, False),
                reset_passwords=True)

    def set_masterauth(self, password):
        self.connection.config_set("masterauth", password)

    def database_sync(self):
        self.connection.save()

    @property
    def ignore_users(self):
        return cfg.get_ignored_users()

    @property
    def ignore_dbs(self):
        return []
