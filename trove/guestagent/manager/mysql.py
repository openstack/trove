import os
from trove.common import cfg
from trove.guestagent import dbaas
from trove.guestagent import backup
from trove.guestagent import volume
from trove.guestagent.manager.mysql_service import MySqlAppStatus
from trove.guestagent.manager.mysql_service import MySqlAdmin
from trove.guestagent.manager.mysql_service import MySqlApp
from trove.instance import models as rd_models
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.openstack.common import periodic_task


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):

    @periodic_task.periodic_task(ticks_between_runs=10)
    def update_status(self, context):
        """Update the status of the MySQL service"""
        MySqlAppStatus.get().update()

    def change_passwords(self, context, users):
        return MySqlAdmin().change_passwords(users)

    def create_database(self, context, databases):
        return MySqlAdmin().create_database(databases)

    def create_user(self, context, users):
        MySqlAdmin().create_user(users)

    def delete_database(self, context, database):
        return MySqlAdmin().delete_database(database)

    def delete_user(self, context, user):
        MySqlAdmin().delete_user(user)

    def get_user(self, context, username, hostname):
        return MySqlAdmin().get_user(username, hostname)

    def grant_access(self, context, username, hostname, databases):
        return MySqlAdmin().grant_access(username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        return MySqlAdmin().revoke_access(username, hostname, database)

    def list_access(self, context, username, hostname):
        return MySqlAdmin().list_access(username, hostname)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return MySqlAdmin().list_databases(limit, marker,
                                           include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return MySqlAdmin().list_users(limit, marker,
                                       include_marker)

    def enable_root(self, context):
        return MySqlAdmin().enable_root()

    def is_root_enabled(self, context):
        return MySqlAdmin().is_root_enabled()

    def _perform_restore(self, backup_id, context, restore_location, app):
        LOG.info(_("Restoring database from backup %s" % backup_id))
        try:
            backup.restore(context, backup_id, restore_location)
        except Exception as e:
            LOG.error(e)
            LOG.error("Error performing restore from backup %s", backup_id)
            app.status.set_status(rd_models.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully"))

    def prepare(self, context, databases, memory_mb, users, device_path=None,
                mount_point=None, backup_id=None):
        """Makes ready DBAAS on a Guest container."""
        MySqlAppStatus.get().begin_mysql_install()
        # status end_mysql_install set with secure()
        app = MySqlApp(MySqlAppStatus.get())
        restart_mysql = False
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            #if a /var/lib/mysql folder exists, back it up.
            if os.path.exists(CONF.mount_point):
                #stop and do not update database
                app.stop_db()
                #rsync exiting data
                if not backup_id:
                    restart_mysql = True
                    device.migrate_data(CONF.mount_point)
            #mount the volume
            device.mount(mount_point)
            LOG.debug(_("Mounted the volume."))
            #check mysql was installed and stopped
            if restart_mysql:
                app.start_mysql()
        app.install_if_needed()
        if backup_id:
            self._perform_restore(backup_id, context, CONF.mount_point, app)
        LOG.info(_("Securing mysql now."))
        app.secure(memory_mb)
        if backup_id and MySqlAdmin().is_root_enabled():
            MySqlAdmin().report_root_enabled(context)
        else:
            app.secure_root()
        app.complete_install_or_restart()

        if databases:
            self.create_database(context, databases)

        if users:
            self.create_user(context, users)

        LOG.info('"prepare" call has finished.')

    def restart(self, context):
        app = MySqlApp(MySqlAppStatus.get())
        app.restart()

    def start_db_with_conf_changes(self, context, updated_memory_size):
        app = MySqlApp(MySqlAppStatus.get())
        app.start_db_with_conf_changes(updated_memory_size)

    def stop_db(self, context, do_not_start_on_reboot=False):
        app = MySqlApp(MySqlAppStatus.get())
        app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """ Gets the filesystem stats for the path given """
        return dbaas.Interrogator().get_filesystem_volume_stats(fs_path)

    def create_backup(self, context, backup_id):
        """
        Entry point for initiating a backup for this guest agents db instance.
        The call currently blocks until the backup is complete or errors. If
        device_path is specified, it will be mounted based to a point specified
        in configuration.

        :param backup_id: the db instance id of the backup task
        """
        backup.backup(context, backup_id)
