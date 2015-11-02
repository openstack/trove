# Copyright 2014 Tesora, Inc.
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
#

import abc

from oslo_log import log as logging
from oslo_service import periodic_task

from trove.common import cfg
from trove.common.i18n import _
from trove.guestagent import dbaas


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):
    """This is the base class for all datastore managers.  Over time, common
    functionality should be pulled back here from the existing managers.
    """

    def __init__(self, manager_name):

        super(Manager, self).__init__(CONF)

        # Manager properties
        self.__manager_name = manager_name
        self.__manager = None
        self.__prepare_error = False

    @property
    def manager_name(self):
        """This returns the passed-in name of the manager."""
        return self.__manager_name

    @property
    def manager(self):
        """This returns the name of the manager."""
        if not self.__manager:
            self.__manager = CONF.datastore_manager or self.__manager_name
        return self.__manager

    @property
    def prepare_error(self):
        return self.__prepare_error

    @prepare_error.setter
    def prepare_error(self, prepare_error):
        self.__prepare_error = prepare_error

    @property
    def configuration_manager(self):
        """If the datastore supports the new-style configuration manager,
        it should override this to return it.
        """
        return None

    @abc.abstractproperty
    def status(self):
        """This should return an instance of a status class that has been
        inherited from datastore.service.BaseDbStatus.  Each datastore
        must implement this property.
        """
        return None

    ################
    # Status related
    ################
    @periodic_task.periodic_task
    def update_status(self, context):
        """Update the status of the trove instance. It is decorated with
        perodic_task so it is called automatically.
        """
        LOG.debug("Update status called.")
        self.status.update()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    #################
    # Prepare related
    #################
    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """Set up datastore on a Guest Instance."""
        LOG.info(_("Starting datastore prepare for '%s'.") % self.manager)
        self.status.begin_install()
        post_processing = True if cluster_config else False
        try:
            self.do_prepare(context, packages, databases, memory_mb,
                            users, device_path, mount_point, backup_info,
                            config_contents, root_password, overrides,
                            cluster_config, snapshot)
        except Exception as ex:
            self.prepare_error = True
            LOG.exception(_("An error occurred preparing datastore: %s") %
                          ex.message)
            raise
        finally:
            LOG.info(_("Ending datastore prepare for '%s'.") % self.manager)
            self.status.end_install(error_occurred=self.prepare_error,
                                    post_processing=post_processing)
        # At this point critical 'prepare' work is done and the instance
        # is now in the correct 'ACTIVE' 'INSTANCE_READY' or 'ERROR' state.
        # Of cource if an error has occurred, none of the code that follows
        # will run.
        LOG.info(_('Completed setup of datastore successfully.'))

        # We only create databases and users automatically for non-cluster
        # instances.
        if not cluster_config:
            try:
                if databases:
                    LOG.debug('Calling add databases.')
                    self.create_database(context, databases)
                if users:
                    LOG.debug('Calling add users.')
                    self.create_user(context, users)
            except Exception as ex:
                LOG.exception(_("An error occurred creating databases/users: "
                                "%s") % ex.message)
                raise

        try:
            LOG.debug('Calling post_prepare.')
            self.post_prepare(context, packages, databases, memory_mb,
                              users, device_path, mount_point, backup_info,
                              config_contents, root_password, overrides,
                              cluster_config, snapshot)
        except Exception as ex:
            LOG.exception(_("An error occurred in post prepare: %s") %
                          ex.message)
            raise

    @abc.abstractmethod
    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info, config_contents,
                   root_password, overrides, cluster_config, snapshot):
        """This is called from prepare when the Trove instance first comes
        online.  'Prepare' is the first rpc message passed from the
        task manager.  do_prepare handles all the base configuration of
        the instance and is where the actual work is done.  Once this method
        completes, the datastore is considered either 'ready' for use (or
        for final connections to other datastores) or in an 'error' state,
        and the status is changed accordingly.  Each datastore must
        implement this method.
        """
        pass

    def post_prepare(self, context, packages, databases, memory_mb, users,
                     device_path, mount_point, backup_info, config_contents,
                     root_password, overrides, cluster_config, snapshot):
        """This is called after prepare has completed successfully.
        Processing done here should be limited to things that will not
        affect the actual 'running' status of the datastore (for example,
        creating databases and users, although these are now handled
        automatically).  Any exceptions are caught, logged and rethrown,
        however no status changes are made and the end-user will not be
        informed of the error.
        """
        LOG.debug('No post_prepare work has been defined.')
        pass

    #####################
    # File System related
    #####################
    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        # TODO(peterstac) - note that fs_path is not used in this method.
        mount_point = CONF.get(self.manager).mount_point
        LOG.debug("Getting file system stats for '%s'" % mount_point)
        return dbaas.get_filesystem_volume_stats(mount_point)

    #################
    # Cluster related
    #################
    def cluster_complete(self, context):
        LOG.debug("Cluster creation complete, starting status checks.")
        self.status.end_install()
