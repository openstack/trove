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
import time

from oslo_log import log as logging

from trove.common import cfg
from trove.common import context as trove_context
from trove.common.i18n import _
from trove.common import instance
from trove.conductor import api as conductor_api
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common import timeutils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class BaseDbStatus(object):
    """
    Answers the question "what is the status of the DB application on
    this box?" The answer can be that the application is not installed, or
    the state of the application is determined by calling a series of
    commands.

    This class also handles saving and load the status of the DB application
    in the database.
    The status is updated whenever the update() method is called, except
    if the state is changed to building or restart mode using the
     "begin_install" and "begin_restart" methods.
    The building mode persists in the database while restarting mode does
    not (so if there is a Python Pete crash update() will set the status to
    show a failure).
    These modes are exited and functionality to update() returns when
    end_install or end_restart() is called, at which point the status again
    reflects the actual status of the DB app.

    This is a base class, subclasses must implement real logic for
    determining current status of DB in _get_actual_db_status()
    """

    _instance = None

    GUESTAGENT_DIR = '~'
    PREPARE_START_FILENAME = '.guestagent.prepare.start'
    PREPARE_END_FILENAME = '.guestagent.prepare.end'

    def __init__(self):
        if self._instance is not None:
            raise RuntimeError("Cannot instantiate twice.")
        self.status = None
        self.restart_mode = False

        self._prepare_completed = None

    @property
    def prepare_completed(self):
        if self._prepare_completed is None:
            # Force the file check
            self.prepare_completed = None
        return self._prepare_completed

    @prepare_completed.setter
    def prepare_completed(self, value):
        # Set the value based on the existence of the file; 'value' is ignored
        # This is required as the value of prepare_completed is cached, so
        # this must be referenced any time the existence of the file changes
        self._prepare_completed = os.path.isfile(
            guestagent_utils.build_file_path(
                self.GUESTAGENT_DIR, self.PREPARE_END_FILENAME))

    def begin_install(self):
        """First call of the DB prepare."""
        prepare_start_file = guestagent_utils.build_file_path(
            self.GUESTAGENT_DIR, self.PREPARE_START_FILENAME)
        operating_system.write_file(prepare_start_file, '')
        self.prepare_completed = False

        self.set_status(instance.ServiceStatuses.BUILDING, True)

    def begin_restart(self):
        """Called before restarting DB server."""
        self.restart_mode = True

    def end_install(self, error_occurred=False, post_processing=False):
        """Called after prepare has ended."""

        # Set the "we're done" flag if there's no error and
        # no post_processing is necessary
        if not (error_occurred or post_processing):
            prepare_end_file = guestagent_utils.build_file_path(
                self.GUESTAGENT_DIR, self.PREPARE_END_FILENAME)
            operating_system.write_file(prepare_end_file, '')
            self.prepare_completed = True

        final_status = None
        if error_occurred:
            final_status = instance.ServiceStatuses.FAILED
        elif post_processing:
            final_status = instance.ServiceStatuses.INSTANCE_READY

        if final_status:
            LOG.info(_("Set final status to %s.") % final_status)
            self.set_status(final_status, force=True)
        else:
            self._end_install_or_restart(True)

    def end_restart(self):
        self.restart_mode = False
        LOG.info(_("Ending restart."))
        self._end_install_or_restart(False)

    def _end_install_or_restart(self, force):
        """Called after DB is installed or restarted.
        Updates the database with the actual DB server status.
        """
        real_status = self._get_actual_db_status()
        LOG.info(_("Current database status is '%s'.") % real_status)
        self.set_status(real_status, force=force)

    def _get_actual_db_status(self):
        raise NotImplementedError()

    @property
    def is_installed(self):
        """
        True if DB app should be installed and attempts to ascertain
        its status won't result in nonsense.
        """
        return self.prepare_completed

    @property
    def _is_restarting(self):
        return self.restart_mode

    @property
    def is_running(self):
        """True if DB server is running."""
        return (self.status is not None and
                self.status == instance.ServiceStatuses.RUNNING)

    def set_status(self, status, force=False):
        """Use conductor to update the DB app status."""

        if force or self.is_installed:
            LOG.debug("Casting set_status message to conductor "
                      "(status is '%s')." % status.description)
            context = trove_context.TroveContext()

            heartbeat = {'service_status': status.description}
            conductor_api.API(context).heartbeat(
                CONF.guest_id, heartbeat, sent=timeutils.float_utcnow())
            LOG.debug("Successfully cast set_status.")
            self.status = status
        else:
            LOG.debug("Prepare has not completed yet, skipping heartbeat.")

    def update(self):
        """Find and report status of DB on this machine.
        The database is updated and the status is also returned.
        """
        if self.is_installed and not self._is_restarting:
            LOG.debug("Determining status of DB server.")
            status = self._get_actual_db_status()
            self.set_status(status)
        else:
            LOG.info(_("DB server is not installed or is in restart mode, so "
                       "for now we'll skip determining the status of DB on "
                       "this instance."))

    def restart_db_service(self, service_candidates, timeout):
        """Restart the database.
        Do not change the service auto-start setting.
        Disable the Trove instance heartbeat updates during the restart.

        1. Stop the database service.
        2. Wait for the database to shutdown.
        3. Start the database service.
        4. Wait for the database to start running.

        :param service_candidates:   List of possible system service names.
        :type service_candidates:    list

        :param timeout:              Wait timeout in seconds.
        :type timeout:               integer

        :raises:              :class:`RuntimeError` on failure.
        """
        try:
            self.begin_restart()
            self.stop_db_service(service_candidates, timeout,
                                 disable_on_boot=False, update_db=False)
            self.start_db_service(service_candidates, timeout,
                                  enable_on_boot=False, update_db=False)
        except Exception as e:
            LOG.exception(e)
            raise RuntimeError(_("Database restart failed."))
        finally:
            self.end_restart()

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
        LOG.info(_("Starting database service."))
        operating_system.start_service(service_candidates)

        LOG.debug("Waiting for database to start up.")
        if not self._wait_for_database_service_status(
                instance.ServiceStatuses.RUNNING, timeout, update_db):
            raise RuntimeError(_("Database failed to start."))

        LOG.info(_("Database has started successfully."))

        if enable_on_boot:
            LOG.info(_("Enable service auto-start on boot."))
            operating_system.enable_service_on_boot(service_candidates)

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
        LOG.info(_("Stopping database service."))
        operating_system.stop_service(service_candidates)

        LOG.debug("Waiting for database to shutdown.")
        if not self._wait_for_database_service_status(
                instance.ServiceStatuses.SHUTDOWN, timeout, update_db):
            raise RuntimeError(_("Database failed to stop."))

        LOG.info(_("Database has stopped successfully."))

        if disable_on_boot:
            LOG.info(_("Disable service auto-start on boot."))
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
            LOG.info(_("Service status did not change to %(status)s "
                       "within the given timeout: %(timeout)ds")
                     % {'status': status, 'timeout': timeout})
            LOG.debug("Attempting to cleanup stalled services.")
            try:
                self.cleanup_stalled_db_services()
            except Exception:
                LOG.debug("Cleanup failed.", exc_info=True)
            return False

        return True

    def wait_for_real_status_to_change_to(self, status, max_time,
                                          update_db=False):
        """
        Waits the given time for the real status to change to the one
        specified. Does not update the publicly viewable status Unless
        "update_db" is True.
        """
        WAIT_TIME = 3
        waited_time = 0
        while waited_time < max_time:
            time.sleep(WAIT_TIME)
            waited_time += WAIT_TIME
            LOG.debug("Waiting for DB status to change to %s." % status)
            actual_status = self._get_actual_db_status()
            LOG.debug("DB status was %s after %d seconds."
                      % (actual_status, waited_time))
            if actual_status == status:
                if update_db:
                    self.set_status(actual_status)
                return True
        LOG.error(_("Timeout while waiting for database status to change."))
        return False

    def cleanup_stalled_db_services(self):
        """An optional datastore-specific code to cleanup stalled
        database services and other resources after a status change timeout.
        """
        LOG.debug("No cleanup action specified for this datastore.")

    def report_root(self, context, user):
        """Use conductor to update the root-enable status."""
        LOG.debug("Casting report_root message to conductor.")
        conductor_api.API(context).report_root(CONF.guest_id, user)
        LOG.debug("Successfully cast report_root.")
