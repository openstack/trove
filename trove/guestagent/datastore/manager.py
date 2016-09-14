# Copyright 2015 Tesora, Inc.
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

from oslo_config import cfg as oslo_cfg
from oslo_log import log as logging
from oslo_service import periodic_task
from oslo_utils import encodeutils

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance
from trove.common.notification import EndNotification
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent import dbaas
from trove.guestagent import guest_log
from trove.guestagent.module import driver_manager
from trove.guestagent.module import module_manager
from trove.guestagent.strategies import replication as repl_strategy
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):
    """This is the base class for all datastore managers.  Over time, common
    functionality should be pulled back here from the existing managers.
    """

    GUEST_LOG_TYPE_LABEL = 'type'
    GUEST_LOG_USER_LABEL = 'user'
    GUEST_LOG_FILE_LABEL = 'file'
    GUEST_LOG_SECTION_LABEL = 'section'
    GUEST_LOG_ENABLE_LABEL = 'enable'
    GUEST_LOG_DISABLE_LABEL = 'disable'
    GUEST_LOG_RESTART_LABEL = 'restart'

    GUEST_LOG_BASE_DIR = '/var/log/trove'
    GUEST_LOG_DATASTORE_DIRNAME = 'datastore'

    GUEST_LOG_DEFS_GUEST_LABEL = 'guest'
    GUEST_LOG_DEFS_GENERAL_LABEL = 'general'
    GUEST_LOG_DEFS_ERROR_LABEL = 'error'
    GUEST_LOG_DEFS_SLOW_QUERY_LABEL = 'slow_query'

    def __init__(self, manager_name):
        super(Manager, self).__init__(CONF)

        # Manager properties
        self.__manager_name = manager_name
        self.__manager = None
        self.__prepare_error = False

        # Guest log
        self._guest_log_context = None
        self._guest_log_loaded_context = None
        self._guest_log_cache = None
        self._guest_log_defs = None

        # Module
        self.module_driver_manager = driver_manager.ModuleDriverManager()

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
    def replication(self):
        """If the datastore supports replication, return an instance of
        the strategy.
        """
        try:
            return repl_strategy.get_instance(self.manager)
        except Exception as ex:
            LOG.debug("Cannot get replication instance for '%s': %s" % (
                      self.manager, ex.message))

        return None

    @property
    def replication_strategy(self):
        """If the datastore supports replication, return the strategy."""
        try:
            return repl_strategy.get_strategy(self.manager)
        except Exception as ex:
            LOG.debug("Cannot get replication strategy for '%s': %s" % (
                      self.manager, ex.message))

        return None

    @abc.abstractproperty
    def status(self):
        """This should return an instance of a status class that has been
        inherited from datastore.service.BaseDbStatus.  Each datastore
        must implement this property.
        """
        return None

    @property
    def configuration_manager(self):
        """If the datastore supports the new-style configuration manager,
        it should override this to return it.
        """
        return None

    @property
    def datastore_log_defs(self):
        """Any datastore-specific log files should be overridden in this dict
        by the corresponding Manager class.

        Format of a dict entry:

        'name_of_log': {self.GUEST_LOG_TYPE_LABEL:
                            Specified by the Enum in guest_log.LogType,
                        self.GUEST_LOG_USER_LABEL:
                            User that owns the file,
                        self.GUEST_LOG_FILE_LABEL:
                            Path on filesystem where the log resides,
                        self.GUEST_LOG_SECTION_LABEL:
                            Section where to put config (if ini style)
                        self.GUEST_LOG_ENABLE_LABEL: {
                            Dict of config_group settings to enable log},
                        self.GUEST_LOG_DISABLE_LABEL: {
                            Dict of config_group settings to disable log},

        See guestagent_log_defs for an example.
        """
        return {}

    @property
    def guestagent_log_defs(self):
        """These are log files that should be available on every Trove
        instance.  By definition, these should be of type LogType.SYS
        """
        log_dir = CONF.get('log_dir', '/var/log/trove/')
        log_file = CONF.get('log_file', 'trove-guestagent.log')
        guestagent_log = guestagent_utils.build_file_path(log_dir, log_file)
        return {
            self.GUEST_LOG_DEFS_GUEST_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.SYS,
                self.GUEST_LOG_USER_LABEL: None,
                self.GUEST_LOG_FILE_LABEL: guestagent_log,
            },
        }

    @property
    def guest_log_defs(self):
        """Return all the guest log defs."""
        if not self._guest_log_defs:
            self._guest_log_defs = dict(self.datastore_log_defs)
            self._guest_log_defs.update(self.guestagent_log_defs)
        return self._guest_log_defs

    @property
    def guest_log_context(self):
        return self._guest_log_context

    @guest_log_context.setter
    def guest_log_context(self, context):
        self._guest_log_context = context

    @property
    def guest_log_cache(self):
        """Make sure the guest_log_cache is loaded and return it."""
        self._refresh_guest_log_cache()
        return self._guest_log_cache

    def _refresh_guest_log_cache(self):
        if self._guest_log_cache:
            # Replace the context if it's changed
            if self._guest_log_loaded_context != self.guest_log_context:
                for log_name in self._guest_log_cache.keys():
                    self._guest_log_cache[log_name].context = (
                        self.guest_log_context)
        else:
            # Load the initial cache
            self._guest_log_cache = {}
            if self.guest_log_context:
                gl_defs = self.guest_log_defs
                try:
                    exposed_logs = CONF.get(self.manager).get(
                        'guest_log_exposed_logs')
                except oslo_cfg.NoSuchOptError:
                    exposed_logs = ''
                LOG.debug("Available log defs: %s" % ",".join(gl_defs.keys()))
                exposed_logs = exposed_logs.lower().replace(',', ' ').split()
                LOG.debug("Exposing log defs: %s" % ",".join(exposed_logs))
                expose_all = 'all' in exposed_logs
                for log_name in gl_defs.keys():
                    gl_def = gl_defs[log_name]
                    exposed = expose_all or log_name in exposed_logs
                    LOG.debug("Building guest log '%s' from def: %s "
                              "(exposed: %s)" %
                              (log_name, gl_def, exposed))
                    self._guest_log_cache[log_name] = guest_log.GuestLog(
                        self.guest_log_context, log_name,
                        gl_def[self.GUEST_LOG_TYPE_LABEL],
                        gl_def[self.GUEST_LOG_USER_LABEL],
                        gl_def[self.GUEST_LOG_FILE_LABEL],
                        exposed)

        self._guest_log_loaded_context = self.guest_log_context

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
    # Instance related
    #################
    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None, modules=None):
        """Set up datastore on a Guest Instance."""
        with EndNotification(context, instance_id=CONF.guest_id):
            self._prepare(context, packages, databases, memory_mb, users,
                          device_path, mount_point, backup_info,
                          config_contents, root_password, overrides,
                          cluster_config, snapshot, modules)

    def _prepare(self, context, packages, databases, memory_mb, users,
                 device_path, mount_point, backup_info,
                 config_contents, root_password, overrides,
                 cluster_config, snapshot, modules):
        LOG.info(_("Starting datastore prepare for '%s'.") % self.manager)
        self.status.begin_install()
        post_processing = True if cluster_config else False
        try:
            # Since all module handling is common, don't pass it down to the
            # individual 'do_prepare' methods.
            self.do_prepare(context, packages, databases, memory_mb,
                            users, device_path, mount_point, backup_info,
                            config_contents, root_password, overrides,
                            cluster_config, snapshot)
            if overrides:
                LOG.info(_("Applying user-specified configuration "
                           "(called from 'prepare')."))
                self.apply_overrides_on_prepare(context, overrides)
        except Exception as ex:
            self.prepare_error = True
            LOG.exception(_("An error occurred preparing datastore: %s") %
                          encodeutils.exception_to_unicode(ex))
            raise
        finally:
            LOG.info(_("Ending datastore prepare for '%s'.") % self.manager)
            self.status.end_install(error_occurred=self.prepare_error,
                                    post_processing=post_processing)
        # At this point critical 'prepare' work is done and the instance
        # is now in the correct 'ACTIVE' 'INSTANCE_READY' or 'ERROR' state.
        # Of cource if an error has occurred, none of the code that follows
        # will run.
        LOG.info(_("Completed setup of '%s' datastore successfully.") %
                 self.manager)

        # The following block performs additional instance initialization.
        # Failures will be recorded, but won't stop the provisioning
        # or change the instance state.
        try:
            if modules:
                LOG.info(_("Applying modules (called from 'prepare')."))
                self.module_apply(context, modules)
                LOG.info(_('Module apply completed.'))
        except Exception as ex:
            LOG.exception(_("An error occurred applying modules: "
                            "%s") % ex.message)
        # The following block performs single-instance initialization.
        # Failures will be recorded, but won't stop the provisioning
        # or change the instance state.
        if not cluster_config:
            try:
                if databases:
                    LOG.info(_("Creating databases (called from 'prepare')."))
                    self.create_database(context, databases)
                    LOG.info(_('Databases created successfully.'))
            except Exception as ex:
                LOG.exception(_("An error occurred creating databases: "
                                "%s") % ex.message)
            try:
                if users:
                    LOG.info(_("Creating users (called from 'prepare')"))
                    self.create_user(context, users)
                    LOG.info(_('Users created successfully.'))
            except Exception as ex:
                LOG.exception(_("An error occurred creating users: "
                                "%s") % ex.message)

            # We only enable-root automatically if not restoring a backup
            # that may already have root enabled in which case we keep it
            # unchanged.
            if root_password and not backup_info:
                try:
                    LOG.info(_("Enabling root user (with password)."))
                    self.enable_root_on_prepare(context, root_password)
                    LOG.info(_('Root enabled successfully.'))
                except Exception as ex:
                    LOG.exception(_("An error occurred enabling root user: "
                                    "%s") % ex.message)

        try:
            LOG.info(_("Calling post_prepare for '%s' datastore.") %
                     self.manager)
            self.post_prepare(context, packages, databases, memory_mb,
                              users, device_path, mount_point, backup_info,
                              config_contents, root_password, overrides,
                              cluster_config, snapshot)
            LOG.info(_("Post prepare for '%s' datastore completed.") %
                     self.manager)
        except Exception as ex:
            LOG.exception(_("An error occurred in post prepare: %s") %
                          ex.message)
            raise

    def apply_overrides_on_prepare(self, context, overrides):
        self.update_overrides(context, overrides)
        self.restart(context)

    def enable_root_on_prepare(self, context, root_password):
        self.enable_root_with_password(context, root_password)

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
        LOG.info(_('No post_prepare work has been defined.'))
        pass

    def pre_upgrade(self, context):
        """Prepares the guest for upgrade, returning a dict to be passed
        to post_upgrade
        """
        return {}

    def post_upgrade(self, context, upgrade_info):
        """Recovers the guest after the image is upgraded using infomation
        from the pre_upgrade step
        """
        pass

    #################
    # Service related
    #################
    @abc.abstractmethod
    def restart(self, context):
        """Restart the database service."""
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

    def mount_volume(self, context, device_path=None, mount_point=None,
                     write_to_fstab=False):
        LOG.debug("Mounting the device %s at the mount point %s." %
                  (device_path, mount_point))
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=write_to_fstab)

    def unmount_volume(self, context, device_path=None, mount_point=None):
        LOG.debug("Unmounting the device %s from the mount point %s." %
                  (device_path, mount_point))
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)

    def resize_fs(self, context, device_path=None, mount_point=None):
        LOG.debug("Resizing the filesystem at %s." % mount_point)
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)

    ###############
    # Configuration
    ###############
    def reset_configuration(self, context, configuration):
        """The default implementation should be sufficient if a
        configuration_manager is provided. Even if one is not, this
        method needs to be implemented to allow the rollback of
        flavor-resize on the guestagent side.
        """
        LOG.debug("Resetting configuration.")
        if self.configuration_manager:
            config_contents = configuration['config_contents']
            self.configuration_manager.save_configuration(config_contents)

    #################
    # Cluster related
    #################
    def cluster_complete(self, context):
        LOG.debug("Cluster creation complete, starting status checks.")
        self.status.end_install()

    #############
    # Log related
    #############
    def guest_log_list(self, context):
        LOG.info(_("Getting list of guest logs."))
        self.guest_log_context = context
        gl_cache = self.guest_log_cache
        result = filter(None, [gl_cache[log_name].show()
                               if gl_cache[log_name].exposed else None
                               for log_name in gl_cache.keys()])
        LOG.info(_("Returning list of logs: %s") % result)
        return result

    def guest_log_action(self, context, log_name, enable, disable,
                         publish, discard):
        if enable and disable:
            raise exception.BadRequest("Cannot enable and disable log '%s'." %
                                       log_name)
        # Enable if we are publishing, unless told to disable
        if publish and not disable:
            enable = True
        LOG.info(_("Processing guest log '%(log)s' "
                   "(enable=%(en)s, disable=%(dis)s, "
                   "publish=%(pub)s, discard=%(disc)s).") %
                 {'log': log_name, 'en': enable, 'dis': disable,
                  'pub': publish, 'disc': discard})
        self.guest_log_context = context
        gl_cache = self.guest_log_cache
        if log_name in gl_cache:
            if ((gl_cache[log_name].type == guest_log.LogType.SYS) and
                    not publish):
                if enable or disable:
                    if enable:
                        action_text = "enable"
                    else:
                        action_text = "disable"
                    raise exception.BadRequest("Cannot %s a SYSTEM log ('%s')."
                                               % (action_text, log_name))
            if gl_cache[log_name].type == guest_log.LogType.USER:
                requires_change = (
                    (gl_cache[log_name].enabled and disable) or
                    (not gl_cache[log_name].enabled and enable))
                if requires_change:
                    restart_required = self.guest_log_enable(
                        context, log_name, disable)
                    if restart_required:
                        self.set_guest_log_status(
                            guest_log.LogStatus.Restart_Required, log_name)
                    gl_cache[log_name].enabled = enable
            log_details = gl_cache[log_name].show()
            if discard:
                log_details = gl_cache[log_name].discard_log()
            if publish:
                log_details = gl_cache[log_name].publish_log()
            LOG.info(_("Details for log '%(log)s': %(det)s") %
                     {'log': log_name, 'det': log_details})
            return log_details

        raise exception.NotFound("Log '%s' is not defined." % log_name)

    def guest_log_enable(self, context, log_name, disable):
        """This method can be overridden by datastore implementations to
        facilitate enabling and disabling USER type logs.  If the logs
        can be enabled with simple configuration group changes, however,
        the code here will probably suffice.
        Must return whether the datastore needs to be restarted in order for
        the logging to begin.
        """
        restart_required = False
        verb = ("Disabling" if disable else "Enabling")
        if self.configuration_manager:
            LOG.debug("%s log '%s'" % (verb, log_name))
            gl_def = self.guest_log_defs[log_name]
            enable_cfg_label = "%s_%s_log" % (self.GUEST_LOG_ENABLE_LABEL,
                                              log_name)
            disable_cfg_label = "%s_%s_log" % (self.GUEST_LOG_DISABLE_LABEL,
                                               log_name)
            restart_required = gl_def.get(self.GUEST_LOG_RESTART_LABEL,
                                          restart_required)
            if disable:
                self._apply_log_overrides(
                    context, enable_cfg_label, disable_cfg_label,
                    gl_def.get(self.GUEST_LOG_DISABLE_LABEL),
                    gl_def.get(self.GUEST_LOG_SECTION_LABEL),
                    restart_required)
            else:
                self._apply_log_overrides(
                    context, disable_cfg_label, enable_cfg_label,
                    gl_def.get(self.GUEST_LOG_ENABLE_LABEL),
                    gl_def.get(self.GUEST_LOG_SECTION_LABEL),
                    restart_required)
        else:
            msg = (_("%(verb)s log '%(log)s' not supported - "
                     "no configuration manager defined!") %
                   {'verb': verb, 'log': log_name})
            LOG.error(msg)
            raise exception.GuestError(original_message=msg)

        return restart_required

    def _apply_log_overrides(self, context, remove_label,
                             apply_label, cfg_values, section_label,
                             restart_required):
        self.configuration_manager.remove_system_override(
            change_id=remove_label)
        if cfg_values:
            config_man_values = cfg_values
            if section_label:
                config_man_values = {section_label: cfg_values}
            # Applying the changes with a group id lower than the one used
            # by user overrides. Any user defined value will override these
            # settings (irrespective of order in which they are applied).
            # See Bug 1542485
            self.configuration_manager._apply_override(
                '10-system-low-priority', apply_label, config_man_values)
        if restart_required:
            self.status.set_status(instance.ServiceStatuses.RESTART_REQUIRED)
        else:
            self.apply_overrides(context, cfg_values)

    def set_guest_log_status(self, status, log_name=None):
        """Sets the status of log_name to 'status' - if log_name is not
        provided, sets the status on all logs.
        """
        gl_cache = self.guest_log_cache
        names = [log_name]
        if not log_name or log_name not in gl_cache:
            names = gl_cache.keys()
        for name in names:
            # If we're already in restart mode and we're asked to set the
            # status to restart, assume enable/disable has been flipped
            # without a restart and set the status to restart done
            if (gl_cache[name].status == guest_log.LogStatus.Restart_Required
                    and status == guest_log.LogStatus.Restart_Required):
                gl_cache[name].status = guest_log.LogStatus.Restart_Completed
            else:
                gl_cache[name].status = status

    def build_log_file_name(self, log_name, owner, datastore_dir=None):
        """Build a log file name based on the log_name and make sure the
        directories exist and are accessible by owner.
        """
        if datastore_dir is None:
            base_dir = self.GUEST_LOG_BASE_DIR
            if not operating_system.exists(base_dir, is_directory=True):
                operating_system.create_directory(
                    base_dir, user=owner, group=owner, force=True,
                    as_root=True)
            datastore_dir = guestagent_utils.build_file_path(
                base_dir, self.GUEST_LOG_DATASTORE_DIRNAME)

        if not operating_system.exists(datastore_dir, is_directory=True):
            operating_system.create_directory(
                datastore_dir, user=owner, group=owner, force=True,
                as_root=True)
        log_file_name = guestagent_utils.build_file_path(
            datastore_dir, '%s-%s.log' % (self.manager, log_name))

        return self.validate_log_file(log_file_name, owner)

    def validate_log_file(self, log_file, owner):
        """Make sure the log file exists and is accessible by owner.
        """
        if not operating_system.exists(log_file, as_root=True):
            operating_system.write_file(log_file, '', as_root=True)

        operating_system.chown(log_file, user=owner, group=owner,
                               as_root=True)
        operating_system.chmod(log_file, FileMode.ADD_USR_RW_GRP_RW_OTH_R,
                               as_root=True)
        LOG.debug("Set log file '%s' as readable" % log_file)
        return log_file

    ################
    # Module related
    ################
    def module_list(self, context, include_contents=False):
        LOG.info(_("Getting list of modules."))
        results = module_manager.ModuleManager.read_module_results(
            is_admin=context.is_admin, include_contents=include_contents)
        LOG.info(_("Returning list of modules: %s") % results)
        return results

    def module_apply(self, context, modules=None):
        LOG.info(_("Applying modules."))
        results = []
        for module_data in modules:
            module = module_data['module']
            id = module.get('id', None)
            module_type = module.get('type', None)
            name = module.get('name', None)
            tenant = module.get('tenant', None)
            datastore = module.get('datastore', None)
            ds_version = module.get('datastore_version', None)
            contents = module.get('contents', None)
            md5 = module.get('md5', None)
            auto_apply = module.get('auto_apply', True)
            visible = module.get('visible', True)
            if not name:
                raise AttributeError(_("Module name not specified"))
            if not contents:
                raise AttributeError(_("Module contents not specified"))
            driver = self.module_driver_manager.get_driver(module_type)
            if not driver:
                raise exception.ModuleTypeNotFound(
                    _("No driver implemented for module type '%s'") %
                    module_type)
            result = module_manager.ModuleManager.apply_module(
                driver, module_type, name, tenant, datastore, ds_version,
                contents, id, md5, auto_apply, visible)
            results.append(result)
        LOG.info(_("Returning list of modules: %s") % results)
        return results

    def module_remove(self, context, module=None):
        LOG.info(_("Removing module."))
        module = module['module']
        id = module.get('id', None)
        module_type = module.get('type', None)
        name = module.get('name', None)
        datastore = module.get('datastore', None)
        ds_version = module.get('datastore_version', None)
        if not name:
            raise AttributeError(_("Module name not specified"))
        driver = self.module_driver_manager.get_driver(module_type)
        if not driver:
            raise exception.ModuleTypeNotFound(
                _("No driver implemented for module type '%s'") %
                module_type)
        module_manager.ModuleManager.remove_module(
            driver, module_type, id, name, datastore, ds_version)
        LOG.info(_("Deleted module: %s") % name)

    ###############
    # Not Supported
    ###############
    def change_passwords(self, context, users):
        LOG.debug("Changing passwords.")
        with EndNotification(context):
            raise exception.DatastoreOperationNotSupported(
                operation='change_passwords', datastore=self.manager)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root', datastore=self.manager)

    def enable_root_with_password(self, context, root_password=None):
        LOG.debug("Enabling root with password.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root_with_password', datastore=self.manager)

    def disable_root(self, context):
        LOG.debug("Disabling root.")
        raise exception.DatastoreOperationNotSupported(
            operation='disable_root', datastore=self.manager)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root was ever enabled.")
        raise exception.DatastoreOperationNotSupported(
            operation='is_root_enabled', datastore=self.manager)

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_backup', datastore=self.manager)

    def _perform_restore(self, backup_info, context, restore_location, app):
        LOG.debug("Performing restore.")
        raise exception.DatastoreOperationNotSupported(
            operation='_perform_restore', datastore=self.manager)

    def create_database(self, context, databases):
        LOG.debug("Creating databases.")
        with EndNotification(context):
            raise exception.DatastoreOperationNotSupported(
                operation='create_database', datastore=self.manager)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_databases', datastore=self.manager)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        with EndNotification(context):
            raise exception.DatastoreOperationNotSupported(
                operation='delete_database', datastore=self.manager)

    def create_user(self, context, users):
        LOG.debug("Creating users.")
        with EndNotification(context):
            raise exception.DatastoreOperationNotSupported(
                operation='create_user', datastore=self.manager)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_users', datastore=self.manager)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        with EndNotification(context):
            raise exception.DatastoreOperationNotSupported(
                operation='delete_user', datastore=self.manager)

    def get_user(self, context, username, hostname):
        LOG.debug("Getting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_user', datastore=self.manager)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating user attributes.")
        with EndNotification(context):
            raise exception.DatastoreOperationNotSupported(
                operation='update_attributes', datastore=self.manager)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting user access.")
        raise exception.DatastoreOperationNotSupported(
            operation='grant_access', datastore=self.manager)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking user access.")
        raise exception.DatastoreOperationNotSupported(
            operation='revoke_access', datastore=self.manager)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing user access.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_access', datastore=self.manager)

    def get_config_changes(self, cluster_config, mount_point=None):
        LOG.debug("Get configuration changes.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_configuration_changes', datastore=self.manager)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_overrides', datastore=self.manager)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides.")
        raise exception.DatastoreOperationNotSupported(
            operation='apply_overrides', datastore=self.manager)

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_replication_snapshot', datastore=self.manager)

    def attach_replication_slave(self, context, snapshot, slave_config):
        LOG.debug("Attaching replication slave.")
        raise exception.DatastoreOperationNotSupported(
            operation='attach_replication_slave', datastore=self.manager)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        raise exception.DatastoreOperationNotSupported(
            operation='detach_replica', datastore=self.manager)

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_replica_context', datastore=self.manager)

    def make_read_only(self, context, read_only):
        LOG.debug("Making datastore read-only.")
        raise exception.DatastoreOperationNotSupported(
            operation='make_read_only', datastore=self.manager)

    def enable_as_master(self, context, replica_source_config):
        LOG.debug("Enabling as master.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_as_master', datastore=self.manager)

    def get_txn_count(self, context):
        LOG.debug("Getting transaction count.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_txn_count', datastore=self.manager)

    def get_latest_txn_id(self, context):
        LOG.debug("Getting latest transaction id.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_latest_txn_id', datastore=self.manager)

    def wait_for_txn(self, context, txn):
        LOG.debug("Waiting for transaction.")
        raise exception.DatastoreOperationNotSupported(
            operation='wait_for_txn', datastore=self.manager)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replication master.")
        raise exception.DatastoreOperationNotSupported(
            operation='demote_replication_master', datastore=self.manager)
