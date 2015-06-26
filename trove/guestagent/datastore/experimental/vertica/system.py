# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from trove.common import utils

ALTER_USER_PASSWORD = "ALTER USER %s IDENTIFIED BY '%s'"
CREATE_DB = ("/opt/vertica/bin/adminTools -t create_db -s"
             " %s -d %s -c %s -D %s -p '%s'")
CREATE_USER = "CREATE USER %s IDENTIFIED BY '%s'"
ENABLE_FOR_USER = "ALTER USER %s DEFAULT ROLE %s"
GRANT_TO_USER = "GRANT %s to %s"
INSTALL_VERTICA = ("/opt/vertica/sbin/install_vertica -s %s"
                   " -d %s -X -N -S default -r"
                   " /vertica.deb -L CE -Y --no-system-checks")
STOP_DB = "/opt/vertica/bin/adminTools -t stop_db -F -d %s -p '%s'"
START_DB = "/opt/vertica/bin/adminTools -t start_db -d %s -p '%s'"
STATUS_ACTIVE_DB = "/opt/vertica/bin/adminTools -t show_active_db"
STATUS_DB_DOWN = "/opt/vertica/bin/adminTools -t db_status -s DOWN"
SET_RESTART_POLICY = ("/opt/vertica/bin/adminTools -t set_restart_policy "
                      "-d %s -p '%s'")
SEND_CONF_TO_SERVER = ("rsync -v -e 'ssh -o "
                       "UserKnownHostsFile=/dev/null -o "
                       "StrictHostKeyChecking=no' --perms --owner --group "
                       "%s %s:%s")
SSH_KEY_GEN = "ssh-keygen -f %s/.ssh/id_rsa -t rsa -N ''"
USER_EXISTS = ("/opt/vertica/bin/vsql -w '%s' -c "
               "\"select 1 from users where user_name = '%s'\" "
               "| grep row | awk '{print $1}' | cut -c2-")
VERTICA_AGENT_SERVICE_COMMAND = "service vertica_agent %s"
VERTICA_CONF = "/etc/vertica.cnf"
INSTALL_TIMEOUT = 1000


def shell_execute(command, command_executor="root"):
    # This method encapsulates utils.execute for 2 purpose:
    # 1. Helps in safe testing.
    # 2. Helps in executing commands as other user, using their environment.

    # Note: This method uses su because using sudo -i -u <user> <command>
    # does not works with vertica installer
    # and it has problems while executing remote commands.
    return utils.execute("sudo", "su", "-", command_executor, "-c", "%s"
                         % command)


def exec_vsql_command(dbadmin_password, command):
    """Executes a VSQL command with the given dbadmin password."""
    return shell_execute("/opt/vertica/bin/vsql -w \'%s\' -c \"%s\""
                         % (dbadmin_password, command), "dbadmin")
