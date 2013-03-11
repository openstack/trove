from reddwarf.guestagent import dbaas
from reddwarf.guestagent import volume
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common import periodic_task
from reddwarf.openstack.common.gettextutils import _
from reddwarf.instance import models as rd_models
import os
LOG = logging.getLogger(__name__)

MYSQL_BASE_DIR = "/var/lib/mysql"


class Manager(periodic_task.PeriodicTasks):

    @periodic_task.periodic_task(ticks_between_runs=10)
    def update_status(self, context):
        """Update the status of the MySQL service"""
        dbaas.MySqlAppStatus.get().update()

    def change_passwords(self, context, users):
        return dbaas.MySqlAdmin().change_passwords(users)

    def create_database(self, context, databases):
        return dbaas.MySqlAdmin().create_database(databases)

    def create_user(self, context, users):
        dbaas.MySqlAdmin().create_user(users)

    def delete_database(self, context, database):
        return dbaas.MySqlAdmin().delete_database(database)

    def delete_user(self, context, user):
        dbaas.MySqlAdmin().delete_user(user)

    def get_user(self, context, username, hostname):
        return dbaas.MySqlAdmin().get_user(username, hostname)

    def grant_access(self, context, username, hostname, databases):
        return dbaas.MySqlAdmin().grant_access(username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        return dbaas.MySqlAdmin().revoke_access(username, hostname, database)

    def list_access(self, context, username, hostname):
        return dbaas.MySqlAdmin().list_access(username, hostname)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return dbaas.MySqlAdmin().list_databases(limit, marker,
                                                 include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return dbaas.MySqlAdmin().list_users(limit, marker,
                                             include_marker)

    def enable_root(self, context):
        return dbaas.MySqlAdmin().enable_root()

    def is_root_enabled(self, context):
        return dbaas.MySqlAdmin().is_root_enabled()

    def prepare(self, context, databases, memory_mb, users, device_path=None,
                mount_point=None):
        """Makes ready DBAAS on a Guest container."""
        dbaas.MySqlAppStatus.get().begin_mysql_install()
        # status end_mysql_install set with secure()
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        restart_mysql = False
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            #if a /var/lib/mysql folder exists, back it up.
            if os.path.exists(MYSQL_BASE_DIR):
                #stop and do not update database
                app.stop_mysql()
                restart_mysql = True
                #rsync exiting data
                device.migrate_data(MYSQL_BASE_DIR)
            #mount the volume
            device.mount(mount_point)
            LOG.debug(_("Mounted the volume."))
            #check mysql was installed and stopped
            if restart_mysql:
                app.start_mysql()
        app.install_if_needed()
        LOG.info("Securing mysql now.")
        app.secure(memory_mb)
        self.create_database(context, databases)
        self.create_user(context, users)
        LOG.info('"prepare" call has finished.')

    def restart(self, context):
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.restart()

    def start_mysql_with_conf_changes(self, context, updated_memory_size):
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.start_mysql_with_conf_changes(updated_memory_size)

    def stop_mysql(self, context, do_not_start_on_reboot=False):
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.stop_mysql(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """ Gets the filesystem stats for the path given """
        return dbaas.Interrogator().get_filesystem_volume_stats(fs_path)
