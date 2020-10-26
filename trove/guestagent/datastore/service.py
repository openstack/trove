# Copyright 2011 OpenStack Foundation
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
import os
import re
import time

from oslo_log import log as logging
from oslo_utils import timeutils

from trove.backup.state import BackupState
from trove.common import cfg
from trove.common import context as trove_context
from trove.common import exception
from trove.common import stream_codecs
from trove.common.i18n import _
from trove.conductor import api as conductor_api
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.utils import docker as docker_util
from trove.instance import service_status

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
BACKUP_LOG_RE = re.compile(r'.*Backup successfully, checksum: '
                           r'(?P<checksum>.*), location: (?P<location>.*)')


class BaseDbStatus(object):
    """
    Answers the question "what is the status of the DB application on
    this box?" The answer can be that the application is not installed, or
    the state of the application is determined by calling a series of
    commands.

    This is a base class, subclasses must implement real logic for
    determining current status of DB in get_actual_db_status()
    """

    GUESTAGENT_DIR = '/opt/trove-guestagent'
    PREPARE_START_FILENAME = '.guestagent.prepare.start'
    PREPARE_END_FILENAME = '.guestagent.prepare.end'

    def __init__(self, docker_client):
        self.status = None
        self.docker_client = docker_client

        self.__prepare_completed = None

    @property
    def prepare_completed(self):
        if self.__prepare_completed is None:
            # Force the file check
            self.__refresh_prepare_completed()
        return self.__prepare_completed

    def __refresh_prepare_completed(self):
        # Set the value of __prepared_completed based on the existence of
        # the file.  This is required as the state is cached so this method
        # must be called any time the existence of the file changes.
        is_file = os.path.isfile(
            guestagent_utils.build_file_path(
                self.GUESTAGENT_DIR, self.PREPARE_END_FILENAME))
        self.__prepare_completed = is_file if is_file else None

    def begin_install(self):
        """First call of the DB prepare."""
        prepare_start_file = guestagent_utils.build_file_path(
            self.GUESTAGENT_DIR, self.PREPARE_START_FILENAME)
        operating_system.write_file(prepare_start_file, '')
        self.__refresh_prepare_completed()

        self.set_status(service_status.ServiceStatuses.BUILDING, True)

    def set_ready(self):
        prepare_end_file = guestagent_utils.build_file_path(
            self.GUESTAGENT_DIR, self.PREPARE_END_FILENAME)
        operating_system.write_file(prepare_end_file, '')
        self.__refresh_prepare_completed()

    def end_install(self, error_occurred=False, post_processing=False):
        """Called after prepare has ended."""

        # Set the "we're done" flag if there's no error and
        # no post_processing is necessary
        if not (error_occurred or post_processing):
            self.set_ready()

        final_status = None
        if error_occurred:
            final_status = service_status.ServiceStatuses.FAILED
        elif post_processing:
            final_status = service_status.ServiceStatuses.INSTANCE_READY

        if final_status:
            LOG.info("Set final status to %s.", final_status)
            self.set_status(final_status, force=True)
        else:
            self._end_install(True)

    def _end_install(self, force):
        """Called after DB is installed.

        Updates the database with the actual DB server status.
        """
        real_status = self.get_actual_db_status()
        LOG.info("Current database status is '%s'.", real_status)
        self.set_status(real_status, force=force)

    def get_actual_db_status(self):
        raise NotImplementedError()

    @property
    def is_installed(self):
        """
        True if DB app should be installed and attempts to ascertain
        its status won't result in nonsense.
        """
        return self.prepare_completed

    @property
    def is_running(self):
        """True if DB server is running."""
        return (self.status is not None and
                self.status in [service_status.ServiceStatuses.RUNNING,
                                service_status.ServiceStatuses.HEALTHY])

    def set_status(self, status, force=False):
        """Use conductor to update the DB app status."""

        if force or self.is_installed:
            LOG.debug("Casting set_status message to conductor "
                      "(status is '%s').", status.description)
            context = trove_context.TroveContext()

            heartbeat = {'service_status': status.description}
            conductor_api.API(context).heartbeat(
                CONF.guest_id, heartbeat,
                sent=timeutils.utcnow_ts(microsecond=True))
            LOG.debug("Successfully cast set_status.")
            self.status = status
        else:
            LOG.debug("Prepare has not completed yet, skipping heartbeat.")

    def update(self):
        """Find and report status of DB on this machine.
        The database is updated and the status is also returned.
        """
        if self.is_installed:
            status = self.get_actual_db_status()
            self.set_status(status)

    def start_db_service(self, service_candidates, timeout,
                         enable_on_boot=True, update_db=False):
        """Start the database service and wait for the database to become
        available.
        The service auto-start will be updated only if the service command
        succeeds.

        :param service_candidates:   List of possible system service names.
        :type service_candidates:    list

        :param timeout:              Wait timeout in seconds.
        :type timeout:               integer

        :param enable_on_boot:       Enable service auto-start.
                                     The auto-start setting will be updated
                                     only if the service command succeeds.
        :type enable_on_boot:        boolean

        :param update_db:            Suppress the Trove instance heartbeat.
        :type update_db:             boolean

        :raises:              :class:`RuntimeError` on failure.
        """
        LOG.info("Starting database service.")
        operating_system.start_service(service_candidates, timeout=timeout)

        self.wait_for_database_service_start(timeout, update_db=update_db)

        if enable_on_boot:
            LOG.info("Enable service auto-start on boot.")
            operating_system.enable_service_on_boot(service_candidates)

    def wait_for_database_service_start(self, timeout, update_db=False):
        """Wait for the database to become available.

        :param timeout:              Wait timeout in seconds.
        :type timeout:               integer

        :param update_db:            Suppress the Trove instance heartbeat.
        :type update_db:             boolean

        :raises:              :class:`RuntimeError` on failure.
        """
        LOG.debug("Waiting for database to start up.")
        if not self._wait_for_database_service_status(
                service_status.ServiceStatuses.RUNNING, timeout, update_db):
            raise RuntimeError(_("Database failed to start."))

        LOG.info("Database has started successfully.")

    def stop_db_service(self, service_candidates, timeout,
                        disable_on_boot=False, update_db=False):
        """Stop the database service and wait for the database to shutdown.

        :param service_candidates:   List of possible system service names.
        :type service_candidates:    list

        :param timeout:              Wait timeout in seconds.
        :type timeout:               integer

        :param disable_on_boot:      Disable service auto-start.
                                     The auto-start setting will be updated
                                     only if the service command succeeds.
        :type disable_on_boot:       boolean

        :param update_db:            Suppress the Trove instance heartbeat.
        :type update_db:             boolean

        :raises:              :class:`RuntimeError` on failure.
        """
        LOG.info("Stopping database service.")
        operating_system.stop_service(service_candidates, timeout=timeout)

        LOG.debug("Waiting for database to shutdown.")
        if not self._wait_for_database_service_status(
                service_status.ServiceStatuses.SHUTDOWN, timeout, update_db):
            raise RuntimeError(_("Database failed to stop."))

        LOG.info("Database has stopped successfully.")

        if disable_on_boot:
            LOG.info("Disable service auto-start on boot.")
            operating_system.disable_service_on_boot(service_candidates)

    def _wait_for_database_service_status(self, status, timeout, update_db):
        """Wait for the given database status.

        :param status:          The status to wait for.
        :type status:           BaseDbStatus

        :param timeout:         Wait timeout in seconds.
        :type timeout:          integer

        :param update_db:       Suppress the Trove instance heartbeat.
        :type update_db:        boolean

        :returns:               True on success, False otherwise.
        """
        if not self.wait_for_real_status_to_change_to(
                status, timeout, update_db):
            LOG.info("Service status did not change to %(status)s "
                     "within the given timeout: %(timeout)ds",
                     {'status': status, 'timeout': timeout})
            LOG.debug("Attempting to cleanup stalled services.")
            try:
                self.cleanup_stalled_db_services()
            except Exception:
                LOG.debug("Cleanup failed.", exc_info=True)
            return False

        return True

    def wait_for_status(self, status, max_time, update_db=False):
        """Waits the given time for the real status to change to the one
        specified.

        The internal status is always updated. The public instance
        state stored in the Trove database is updated only if "update_db" is
        True.
        """
        end_time = time.time() + max_time

        # since python does not support a real do-while loop, we have
        # to emulate one. Hence these shenanigans. We force at least
        # one pass into the loop and therefore it is safe that
        # actual_status is initialized in the loop while it is used
        # outside.
        loop = True

        # We need 3 (by default) consecutive success db connections for status
        # 'HEALTHY'
        healthy_count = 0

        while loop:
            self.status = self.get_actual_db_status()
            if self.status == status:
                if (status == service_status.ServiceStatuses.HEALTHY and
                        healthy_count < 2):
                    healthy_count += 1
                    time.sleep(CONF.state_change_poll_time)
                    continue

                if update_db:
                    self.set_status(self.status)
                return True

            # should we remain in this loop? this is the thing
            # that emulates the do-while construct.
            loop = (time.time() < end_time)

            # no point waiting if our time is up and we're
            # just going to error out anyway.
            if loop:
                LOG.debug("Waiting for DB status to change from "
                          "%(actual_status)s to %(status)s.",
                          {"actual_status": self.status, "status": status})

                time.sleep(CONF.state_change_poll_time)

        LOG.error("Timeout while waiting for database status to change."
                  "Expected state %(status)s, "
                  "current state is %(actual_status)s",
                  {"status": status, "actual_status": self.status})
        return False

    def cleanup_stalled_db_services(self):
        """An optional datastore-specific code to cleanup stalled
        database services and other resources after a status change timeout.
        """
        LOG.debug("No cleanup action specified for this datastore.")

    def report_root(self, context):
        """Use conductor to update the root-enable status."""
        LOG.debug("Casting report_root message to conductor.")
        conductor_api.API(context).report_root(CONF.guest_id)
        LOG.debug("Successfully cast report_root.")


class BaseDbApp(object):
    CFG_CODEC = stream_codecs.IniCodec()

    def __init__(self, status, docker_client):
        self.status = status
        self.docker_client = docker_client

    @classmethod
    def get_client_auth_file(cls, file="os_admin.cnf"):
        # Save the password inside the mount point directory so we could
        # restore everyting when rebuilding the instance.
        conf_dir = guestagent_utils.get_conf_dir()
        return guestagent_utils.build_file_path(conf_dir, file)

    @classmethod
    def get_auth_password(cls, file="os_admin.cnf"):
        auth_config = operating_system.read_file(
            cls.get_client_auth_file(file), codec=cls.CFG_CODEC, as_root=True)
        return auth_config['client']['password']

    @classmethod
    def save_password(cls, user, password):
        content = {
            'client': {
                'user': user,
                'password': password,
                'host': "localhost"
            }
        }

        conf_dir = guestagent_utils.get_conf_dir()
        operating_system.write_file(
            f'{conf_dir}/{user}.cnf', content, codec=cls.CFG_CODEC,
            as_root=True)

    def remove_overrides(self):
        self.configuration_manager.remove_user_override()

    def reset_configuration(self, configuration):
        pass

    def stop_db(self, update_db=False):
        LOG.info("Stopping database.")

        try:
            docker_util.stop_container(self.docker_client)
        except Exception:
            LOG.exception("Failed to stop database")
            raise exception.TroveError("Failed to stop database")

        if not self.status.wait_for_status(
            service_status.ServiceStatuses.SHUTDOWN,
            CONF.state_change_wait_time, update_db
        ):
            raise exception.TroveError("Failed to stop database")

    def start_db_with_conf_changes(self, config_contents, ds_version):
        LOG.info(f"Starting database service with new configuration and "
                 f"datastore version {ds_version}.")

        if self.status.is_running:
            LOG.info("Stopping database before applying changes.")
            self.stop_db()

        self.reset_configuration(config_contents)
        self.start_db(update_db=True, ds_version=ds_version)

    def get_backup_image(self):
        return cfg.get_configuration_property('backup_docker_image')

    def get_backup_strategy(self):
        return cfg.get_configuration_property('backup_strategy')

    def create_backup(self, context, backup_info, volumes_mapping={},
                      need_dbuser=True, extra_params=''):
        storage_driver = CONF.storage_strategy
        backup_driver = self.get_backup_strategy()
        incremental = ''
        backup_type = 'full'
        if backup_info.get('parent'):
            incremental = (
                f'--incremental '
                f'--parent-location={backup_info["parent"]["location"]} '
                f'--parent-checksum={backup_info["parent"]["checksum"]}')
            backup_type = 'incremental'

        name = 'db_backup'
        backup_id = backup_info["id"]
        image = self.get_backup_image()
        os_cred = (f"--os-token={context.auth_token} "
                   f"--os-auth-url={CONF.service_credentials.auth_url} "
                   f"--os-tenant-id={context.project_id}")

        db_userinfo = ''
        if need_dbuser:
            admin_pass = self.get_auth_password()
            db_userinfo = (f"--db-host=127.0.0.1 --db-user=os_admin "
                           f"--db-password={admin_pass}")

        swift_metadata = (
            f'datastore:{backup_info["datastore"]},'
            f'datastore_version:{backup_info["datastore_version"]}'
        )
        swift_container = (backup_info.get('swift_container') or
                           CONF.backup_swift_container)
        swift_params = (f'--swift-extra-metadata={swift_metadata} '
                        f'--swift-container={swift_container}')

        command = (
            f'/usr/bin/python3 main.py --backup --backup-id={backup_id} '
            f'--storage-driver={storage_driver} --driver={backup_driver} '
            f'{os_cred} '
            f'{db_userinfo} '
            f'{swift_params} '
            f'{incremental} '
            f'{extra_params}'
        )

        # Update backup status in db
        conductor = conductor_api.API(context)
        mount_point = cfg.get_configuration_property('mount_point')
        stats = guestagent_utils.get_filesystem_volume_stats(mount_point)
        backup_state = {
            'backup_id': backup_id,
            'size': stats.get('used', 0.0),
            'state': BackupState.BUILDING,
            'backup_type': backup_type
        }
        conductor.update_backup(CONF.guest_id,
                                sent=timeutils.utcnow_ts(microsecond=True),
                                **backup_state)
        LOG.debug(f"Updated state for backup {backup_id} to {backup_state}")

        # Start to run backup inside a separate docker container
        try:
            LOG.info(f'Starting to create backup {backup_id}, '
                     f'command: {command}')
            output, ret = docker_util.run_container(
                self.docker_client, image, name,
                volumes=volumes_mapping, command=command)
            result = output[-1]
            if not ret:
                msg = f'Failed to run backup container, error: {result}'
                LOG.error(msg)
                raise Exception(msg)

            backup_result = BACKUP_LOG_RE.match(result)
            if backup_result:
                backup_state.update({
                    'checksum': backup_result.group('checksum'),
                    'location': backup_result.group('location'),
                    'success': True,
                    'state': BackupState.COMPLETED,
                })
            else:
                msg = f'Cannot parse backup output: {result}'
                LOG.error(msg)
                backup_state.update({
                    'success': False,
                    'state': BackupState.FAILED,
                })
                raise Exception(msg)
        except Exception as err:
            LOG.error("Failed to create backup %s", backup_id)
            backup_state.update({
                'success': False,
                'state': BackupState.FAILED,
            })
            raise exception.TroveError(
                "Failed to create backup %s, error: %s" %
                (backup_id, str(err))
            )
        finally:
            LOG.info("Completed backup %s.", backup_id)
            conductor.update_backup(
                CONF.guest_id,
                sent=timeutils.utcnow_ts(microsecond=True),
                **backup_state)
            LOG.debug("Updated state for %s to %s.", backup_id, backup_state)
