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
import operator

import docker
from oslo_config import cfg as oslo_cfg
from oslo_log import log as logging
from oslo_service import periodic_task

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.notification import EndNotification
from trove.guestagent import dbaas
from trove.guestagent import guest_log
from trove.guestagent import volume
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.module import driver_manager
from trove.guestagent.module import module_manager
from trove.guestagent.strategies import replication as repl_strategy
from trove.instance import service_status

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

    MODULE_APPLY_TO_ALL = module_manager.ModuleManager.MODULE_APPLY_TO_ALL

    _docker_client = None

    @property
    def docker_client(self):
        if self._docker_client:
            return self._docker_client

        self._docker_client = docker.from_env()
        return self._docker_client

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

        # Drivers should implement
        self.adm = None
        self.app = None
        self.status = None

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

    @property
    def replication(self):
        """If the datastore supports replication, return an instance of
        the strategy.
        """
        try:
            return repl_strategy.get_instance(self.manager)
        except Exception as ex:
            LOG.warning("Cannot get replication instance for '%(manager)s': "
                        "%(msg)s", {'manager': self.manager, 'msg': str(ex)})

        return None

    @property
    def replication_strategy(self):
        """If the datastore supports replication, return the strategy."""
        try:
            return repl_strategy.get_strategy(self.manager)
        except Exception as ex:
            LOG.debug("Cannot get replication strategy for '%(manager)s': "
                      "%(msg)s", {'manager': self.manager, 'msg': str(ex)})

        return None

    @property
    def guestagent_log_defs(self):
        """These are log files that should be available on every Trove
        instance.  By definition, these should be of type LogType.SYS
        """
        log_dir = CONF.log_dir or '/var/log/trove/'
        log_file = CONF.log_file or 'trove-guestagent.log'
        guestagent_log = guestagent_utils.build_file_path(log_dir, log_file)
        return {
            self.GUEST_LOG_DEFS_GUEST_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.SYS,
                self.GUEST_LOG_USER_LABEL: None,
                self.GUEST_LOG_FILE_LABEL: guestagent_log,
            },
        }

    @property
    def guest_log_context(self):
        return self._guest_log_context

    @guest_log_context.setter
    def guest_log_context(self, context):
        self._guest_log_context = context

    @periodic_task.periodic_task
    def update_status(self, context):
        """Update the status of the trove instance."""
        if not self.status.is_installed:
            LOG.info("Database service is not installed, skip status check")
            return

        LOG.debug("Starting to check database service status")

        status = self.get_service_status()
        self.status.set_status(status)

    def get_service_status(self):
        return self.status.get_actual_db_status()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    #################
    # Instance related
    #################
    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None, modules=None,
                ds_version=None):
        """Set up datastore on a Guest Instance."""
        with EndNotification(context, instance_id=CONF.guest_id):
            self._prepare(context, packages, databases, memory_mb, users,
                          device_path, mount_point, backup_info,
                          config_contents, root_password, overrides,
                          cluster_config, snapshot, modules,
                          ds_version=ds_version)

    def _prepare(self, context, packages, databases, memory_mb, users,
                 device_path, mount_point, backup_info,
                 config_contents, root_password, overrides,
                 cluster_config, snapshot, modules, ds_version=None):
        LOG.info("Starting datastore prepare for '%s:%s'.", self.manager,
                 ds_version)
        self.status.begin_install()
        post_processing = True if cluster_config else False
        try:
            # Since all module handling is common, don't pass it down to the
            # individual 'do_prepare' methods.
            self.do_prepare(context, packages, databases, memory_mb,
                            users, device_path, mount_point, backup_info,
                            config_contents, root_password, overrides,
                            cluster_config, snapshot, ds_version=ds_version)
        except Exception as ex:
            self.prepare_error = True
            LOG.exception("Failed to prepare datastore: %s", ex)
            raise
        finally:
            LOG.info("Ending datastore prepare for '%s'.", self.manager)
            self.status.end_install(error_occurred=self.prepare_error,
                                    post_processing=post_processing)
        # At this point critical 'prepare' work is done and the instance
        # is now in the correct 'ACTIVE' 'INSTANCE_READY' or 'ERROR' state.
        # Of cource if an error has occurred, none of the code that follows
        # will run.
        LOG.info("Completed setup of '%s' datastore successfully.",
                 self.manager)

        # The following block performs additional instance initialization.
        # Failures will be recorded, but won't stop the provisioning
        # or change the instance state.
        try:
            if modules:
                LOG.info("Applying modules (called from 'prepare').")
                self.module_apply(context, modules)
                LOG.info('Module apply completed.')
        except Exception as ex:
            LOG.exception("An error occurred applying modules: "
                          "%s", str(ex))

        # The following block performs single-instance initialization.
        # Failures will be recorded, but won't stop the provisioning
        # or change the instance state.
        if not cluster_config:
            try:
                if databases:
                    LOG.info("Creating databases (called from 'prepare').")
                    self.create_database(context, databases)
                    LOG.info('Databases created successfully.')
            except Exception as ex:
                LOG.warning("An error occurred creating databases: %s",
                            str(ex))
            try:
                if users:
                    LOG.info("Creating users (called from 'prepare')")
                    self.create_user(context, users)
                    LOG.info('Users created successfully.')
            except Exception as ex:
                LOG.warning("An error occurred creating users: "
                            "%s", str(ex))

            # We only enable-root automatically if not restoring a backup
            # that may already have root enabled in which case we keep it
            # unchanged.
            if root_password and not backup_info:
                try:
                    LOG.info("Enabling root user (with password).")
                    self.enable_root_on_prepare(context, root_password)
                    LOG.info('Root enabled successfully.')
                except Exception as ex:
                    LOG.exception("An error occurred enabling root user: "
                                  "%s", str(ex))

        try:
            LOG.info("Starting post prepare for '%s' datastore.", self.manager)
            self.post_prepare(context, packages, databases, memory_mb,
                              users, device_path, mount_point, backup_info,
                              config_contents, root_password, overrides,
                              cluster_config, snapshot)
            LOG.info("Post prepare for '%s' datastore completed.",
                     self.manager)
        except Exception as ex:
            LOG.exception("An error occurred in post prepare: %s",
                          str(ex))
            raise

    @abc.abstractmethod
    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info, config_contents,
                   root_password, overrides, cluster_config, snapshot,
                   ds_version=None):
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
        LOG.info('No post_prepare work has been defined.')
        pass

    def start_db_with_conf_changes(self, context, config_contents, ds_version):
        """Start the database with given configuration.

        This method is called after resize.
        """
        self.app.start_db_with_conf_changes(config_contents, ds_version)

    def stop_db(self, context):
        self.app.stop_db()

    def restart(self, context):
        self.app.restart()

    def rebuild(self, context, ds_version, config_contents=None,
                config_overrides=None):
        raise exception.DatastoreOperationNotSupported(
            operation='rebuild', datastore=self.manager)

    def pre_upgrade(self, context):
        """Prepares the guest for upgrade, returning a dict to be passed
        to post_upgrade
        """
        return {}

    def upgrade(self, context, upgrade_info):
        """Upgrade the database."""
        pass

    def post_upgrade(self, context, upgrade_info):
        """Recovers the guest after the image is upgraded using information
        from the pre_upgrade step
        """
        pass

    #####################
    # File System related
    #####################
    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        # TODO(peterstac) - note that fs_path is not used in this method.
        mount_point = CONF.get(self.manager).mount_point
        LOG.debug("Getting file system stats for '%s'", mount_point)
        return dbaas.get_filesystem_volume_stats(mount_point)

    def mount_volume(self, context, device_path=None, mount_point=None,
                     write_to_fstab=False):
        LOG.debug("Mounting the device %(path)s at the mount point "
                  "%(mount_point)s.", {'path': device_path,
                                       'mount_point': mount_point})
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=write_to_fstab)

    def unmount_volume(self, context, device_path=None, mount_point=None):
        LOG.debug("Unmounting the device %(path)s from the mount point "
                  "%(mount_point)s.", {'path': device_path,
                                       'mount_point': mount_point})
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)

    def resize_fs(self, context, device_path=None, mount_point=None,
                  online=False):
        LOG.info(f"Resizing the filesystem at {mount_point}, online: {online}")
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point, online=online)

    ###############
    # Configuration
    ###############
    def reset_configuration(self, context, configuration):
        """Reset database base configuration.

        The default implementation should be sufficient if a
        configuration_manager is provided. Even if one is not, this
        method needs to be implemented to allow the rollback of
        flavor-resize on the guestagent side.
        """
        if self.configuration_manager:
            LOG.info("Resetting configuration.")
            config_contents = configuration['config_contents']
            self.configuration_manager.reset_configuration(config_contents)

    def apply_overrides_on_prepare(self, context, overrides):
        self.update_overrides(context, overrides)
        self.restart(context)

    def update_overrides(self, context, overrides, remove=False):
        LOG.info(f"Updating config options: {overrides}, remove={remove}")
        if remove:
            self.app.remove_overrides()
        self.app.update_overrides(overrides)

    def apply_overrides(self, context, overrides):
        raise exception.DatastoreOperationNotSupported(
            operation='apply_overrides', datastore=self.manager)

    #################
    # Cluster related
    #################
    def cluster_complete(self, context):
        LOG.info("Cluster creation complete, starting status checks.")
        self.status.end_install()

    #############
    # Log related
    #############
    def get_datastore_log_defs(self):
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

    def is_log_enabled(self, logname):
        return False

    def get_guest_log_defs(self):
        """Return all the guest log defs."""
        if not self._guest_log_defs:
            self._guest_log_defs = dict(self.get_datastore_log_defs())
            self._guest_log_defs.update(self.guestagent_log_defs)
        return self._guest_log_defs

    def get_guest_log_cache(self):
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
                gl_defs = self.get_guest_log_defs()
                try:
                    exposed_logs = CONF.get(self.manager).get(
                        'guest_log_exposed_logs')
                except oslo_cfg.NoSuchOptError:
                    exposed_logs = ''
                LOG.debug("Available log defs: %s", ",".join(gl_defs.keys()))
                exposed_logs = exposed_logs.lower().replace(',', ' ').split()
                LOG.debug("Exposing log defs: %s", ",".join(exposed_logs))
                expose_all = 'all' in exposed_logs

                for log_name in gl_defs.keys():
                    gl_def = gl_defs[log_name]
                    exposed = expose_all or log_name in exposed_logs
                    guestlog = guest_log.GuestLog(
                        self.guest_log_context, log_name,
                        gl_def[self.GUEST_LOG_TYPE_LABEL],
                        gl_def[self.GUEST_LOG_USER_LABEL],
                        gl_def[self.GUEST_LOG_FILE_LABEL],
                        exposed)

                    if (gl_def[self.GUEST_LOG_TYPE_LABEL] ==
                        guest_log.LogType.USER):
                        guestlog.enabled = self.is_log_enabled(log_name)
                        guestlog.status = (guest_log.LogStatus.Enabled
                                           if guestlog.enabled
                                           else guest_log.LogStatus.Disabled)

                    self._guest_log_cache[log_name] = guestlog

        self._guest_log_loaded_context = self.guest_log_context

    def guest_log_list(self, context):
        LOG.info("Getting list of guest logs.")
        self.guest_log_context = context
        gl_cache = self.get_guest_log_cache()
        result = filter(None, [gl_cache[log_name].show()
                               if gl_cache[log_name].exposed else None
                               for log_name in gl_cache.keys()])
        return result

    def guest_log_action(self, context, log_name, enable, disable,
                         publish, discard):
        if enable and disable:
            raise exception.BadRequest("Cannot enable and disable log '%s'." %
                                       log_name)
        # Enable if we are publishing, unless told to disable
        if publish and not disable:
            enable = True
        LOG.info("Processing guest log '%(log)s' "
                 "(enable=%(en)s, disable=%(dis)s, "
                 "publish=%(pub)s, discard=%(disc)s).",
                 {'log': log_name, 'en': enable, 'dis': disable,
                  'pub': publish, 'disc': discard})

        self.guest_log_context = context
        gl_cache = self.get_guest_log_cache()

        if log_name in gl_cache:
            LOG.debug(f"Found log {log_name}, type={gl_cache[log_name].type}, "
                      f"enable={gl_cache[log_name].enabled}")

            # system log can only be published
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
                    self.guest_log_enable(context, log_name, disable)
                    gl_cache[log_name].enabled = enable
                    gl_cache[log_name].status = (
                        guest_log.LogStatus.Enabled
                        if enable
                        else guest_log.LogStatus.Disabled
                    )

            log_details = gl_cache[log_name].show()
            if discard:
                log_details = gl_cache[log_name].discard_log()
            if publish:
                log_details = gl_cache[log_name].publish_log()

            LOG.info("Details for log '%(log)s': %(det)s",
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
            LOG.debug("%(verb)s log '%(log)s'", {'verb': verb,
                                                 'log': log_name})
            gl_def = self.get_guest_log_defs()[log_name]
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
            log_fmt = ("%(verb)s log '%(log)s' not supported - "
                       "no configuration manager defined!")
            exc_fmt = _("%(verb)s log '%(log)s' not supported - "
                        "no configuration manager defined!")
            msg_content = {'verb': verb, 'log': log_name}
            LOG.error(log_fmt, msg_content)
            raise exception.GuestError(
                original_message=(exc_fmt % msg_content))

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
            self.configuration_manager.apply_system_override(
                config_man_values, change_id=apply_label, pre_user=True)
        if restart_required:
            self.status.set_status(
                service_status.ServiceStatuses.RESTART_REQUIRED)
        else:
            self.apply_overrides(context, cfg_values)

    def get_log_status(self, label):
        self.configuration_manager.get_value(label)

    def build_log_file_name(self, log_name, owner, datastore_dir=None):
        """Build a log file name based on the log_name and make sure the
        directories exist and are accessible by owner.
        """
        if datastore_dir is None:
            base_dir = self.GUEST_LOG_BASE_DIR
            if not operating_system.exists(base_dir, is_directory=True):
                operating_system.ensure_directory(
                    base_dir, user=owner, group=owner, force=True,
                    as_root=True)
            datastore_dir = guestagent_utils.build_file_path(
                base_dir, self.GUEST_LOG_DATASTORE_DIRNAME)

        if not operating_system.exists(datastore_dir, is_directory=True):
            operating_system.ensure_directory(
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

        return log_file

    ################
    # Module related
    ################
    def module_list(self, context, include_contents=False):
        LOG.info("Getting list of modules.")
        results = module_manager.ModuleManager.read_module_results(
            is_admin=context.is_admin, include_contents=include_contents)
        LOG.info("Returning list of modules: %s", results)
        return results

    def module_apply(self, context, modules=None):
        LOG.info("Applying modules.")
        results = []
        modules = [data['module'] for data in modules]
        try:
            # make sure the modules are applied in the correct order
            modules.sort(key=operator.itemgetter('apply_order'))
            modules.sort(key=operator.itemgetter('priority_apply'),
                         reverse=True)
        except KeyError:
            # If we don't have ordering info then maybe we're running
            # a version of the module feature before ordering was
            # introduced.  In that case, since we don't have any
            # way to order the modules we should just continue.
            pass
        for module in modules:
            id = module.get('id', None)
            module_type = module.get('type', None)
            name = module.get('name', None)
            tenant = module.get('tenant', self.MODULE_APPLY_TO_ALL)
            datastore = module.get('datastore', self.MODULE_APPLY_TO_ALL)
            ds_version = module.get('datastore_version',
                                    self.MODULE_APPLY_TO_ALL)
            contents = module.get('contents', None)
            md5 = module.get('md5', None)
            auto_apply = module.get('auto_apply', True)
            visible = module.get('visible', True)
            is_admin = module.get('is_admin', None)
            if is_admin is None:
                # fall back to the old method of checking for an admin option
                is_admin = (tenant == self.MODULE_APPLY_TO_ALL or
                            not visible or
                            auto_apply)
            if not name:
                raise AttributeError(_("Module name not specified"))
            if not contents:
                raise AttributeError(_("Module contents not specified"))
            driver = self.module_driver_manager.get_driver(module_type)
            if not driver:
                raise exception.ModuleTypeNotFound(
                    _("No driver implemented for module type '%s'") %
                    module_type)
            if (datastore and datastore != self.MODULE_APPLY_TO_ALL and
                    datastore != CONF.datastore_manager):
                reason = (_("Module not valid for datastore %s") %
                          CONF.datastore_manager)
                raise exception.ModuleInvalid(reason=reason)
            result = module_manager.ModuleManager.apply_module(
                driver, module_type, name, tenant, datastore, ds_version,
                contents, id, md5, auto_apply, visible, is_admin)
            results.append(result)
        LOG.info("Returning list of modules: %s", results)
        return results

    def module_remove(self, context, module=None):
        LOG.info("Removing module.")
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
        LOG.info("Deleted module: %s", name)

    ################
    # Backup and restore
    ################
    def create_backup(self, context, backup_info):
        """Create backup for the database.

        :param context: User context object.
        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """
        pass

    def perform_restore(self, context, restore_location, backup_info):
        LOG.info("Starting to restore database from backup %s, "
                 "backup_info: %s", backup_info['id'], backup_info)

        if (backup_info["location"].endswith('.enc') and
                not CONF.backup_aes_cbc_key):
            self.status.set_status(service_status.ServiceStatuses.FAILED)
            raise exception.TroveError('Decryption key not configured for '
                                       'encrypted backup.')

        try:
            self.app.restore_backup(context, backup_info, restore_location)
        except Exception:
            LOG.error("Failed to restore from backup %s.", backup_info['id'])
            self.status.set_status(service_status.ServiceStatuses.FAILED)
            raise

        LOG.info("Finished restore data from backup %s", backup_info['id'])

    ################
    # Database and user management
    ################
    def create_database(self, context, databases):
        with EndNotification(context):
            return self.adm.create_databases(databases)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return self.adm.list_databases(limit, marker, include_marker)

    def delete_database(self, context, database):
        with EndNotification(context):
            return self.adm.delete_database(database)

    def change_passwords(self, context, users):
        with EndNotification(context):
            self.adm.change_passwords(users)

    def get_root_password(self, context):
        raise exception.DatastoreOperationNotSupported(
            operation='get_root_password', datastore=self.manager)

    def enable_root(self, context):
        LOG.info("Enabling root for the database.")
        return self.adm.enable_root()

    def enable_root_on_prepare(self, context, root_password):
        self.enable_root_with_password(context, root_password)

    def enable_root_with_password(self, context, root_password=None):
        return self.adm.enable_root(root_password)

    def disable_root(self, context):
        LOG.info("Disabling root for the database.")
        return self.adm.disable_root()

    def is_root_enabled(self, context):
        return self.adm.is_root_enabled()

    def create_user(self, context, users):
        with EndNotification(context):
            self.adm.create_users(users)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return self.adm.list_users(limit, marker, include_marker)

    def delete_user(self, context, user):
        with EndNotification(context):
            self.adm.delete_user(user)

    def get_user(self, context, username, hostname):
        return self.adm.get_user(username, hostname)

    def update_attributes(self, context, username, hostname, user_attrs):
        with EndNotification(context):
            self.adm.update_attributes(username, hostname, user_attrs)

    def grant_access(self, context, username, hostname, databases):
        return self.adm.grant_access(username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        return self.adm.revoke_access(username, hostname, database)

    def list_access(self, context, username, hostname):
        return self.adm.list_access(username, hostname)

    ################
    # Replication related
    ################
    def backup_required_for_replication(self, context):
        return self.replication.backup_required_for_replication()

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.info("Getting replication snapshot, snapshot_info: %s",
                 snapshot_info)

        self.replication.enable_as_master(self.app, replica_source_config)
        LOG.info('Enabled as replication master')

        snapshot_id, log_position = self.replication.snapshot_for_replication(
            context, self.app, self.adm, None, snapshot_info)

        volume_stats = self.get_filesystem_stats(context, None)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': self.manager,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
            'master': self.replication.get_master_ref(self.app, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot

    def attach_replica(self, context, snapshot, slave_config, restart=False):
        raise exception.DatastoreOperationNotSupported(
            operation='attach_replication_slave', datastore=self.manager)

    def detach_replica(self, context, for_failover=False):
        """Running on replica, detach from the primary."""
        LOG.info("Detaching replica.")
        replica_info = self.replication.detach_slave(self.app, for_failover)
        return replica_info

    def get_replica_context(self, context):
        """Running on primary."""
        LOG.info("Getting replica context.")
        replica_info = self.replication.get_replica_context(self.app, self.adm)
        return replica_info

    def make_read_only(self, context, read_only):
        raise exception.DatastoreOperationNotSupported(
            operation='make_read_only', datastore=self.manager)

    def enable_as_master(self, context, replica_source_config):
        LOG.info("Enable as master")
        self.replication.enable_as_master(self.app, replica_source_config)

    def demote_replication_master(self, context):
        LOG.info("Demoting replication master.")
        self.replication.demote_master(self.app)

    def get_txn_count(self, context):
        LOG.debug("Getting transaction count.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_txn_count', datastore=self.manager)

    def get_latest_txn_id(self, context):
        raise exception.DatastoreOperationNotSupported(
            operation='get_latest_txn_id', datastore=self.manager)

    def wait_for_txn(self, context, txn):
        raise exception.DatastoreOperationNotSupported(
            operation='wait_for_txn', datastore=self.manager)
