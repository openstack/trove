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

import re

from trove.common.i18n import _
from trove.common import utils

ALTER_DB_CFG = "ALTER DATABASE %s SET %s = %s"
ALTER_DB_RESET_CFG = "ALTER DATABASE %s CLEAR %s"
ALTER_USER_PASSWORD = "ALTER USER %s IDENTIFIED BY '%s'"
ADD_DB_TO_NODE = ("/opt/vertica/bin/adminTools -t db_add_node -a"
                  " %s -d %s -p '%s'")
REMOVE_DB_FROM_NODE = ("/opt/vertica/bin/adminTools -t db_remove_node -s"
                       " %s -d %s -i -p '%s'")
CREATE_DB = ("echo yes | /opt/vertica/bin/adminTools -t create_db -s"
             " %s -d %s -c %s -D %s -p '%s'")
CREATE_USER = "CREATE USER %s IDENTIFIED BY '%s'"
ENABLE_FOR_USER = "ALTER USER %s DEFAULT ROLE %s"
GRANT_TO_USER = "GRANT %s to %s"
INSTALL_VERTICA = ("/opt/vertica/sbin/install_vertica -s %s"
                   " -d %s -X -N -S default -r"
                   " /vertica.deb -L CE -Y --no-system-checks"
                   " --ignore-aws-instance-type"
                   " --ignore-install-config")
MARK_DESIGN_KSAFE = "SELECT MARK_DESIGN_KSAFE(%s)"
NODE_STATUS = "SELECT node_state FROM nodes where node_state <> '%s'"
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
UPDATE_VERTICA = ("/opt/vertica/sbin/update_vertica %s %s "
                  " -d %s -X -N -S default -r"
                  " /vertica.deb -L CE -Y --no-system-checks"
                  " --ignore-aws-instance-type"
                  " --ignore-install-config")
UPDATE_REMOVE = ("/opt/vertica/sbin/update_vertica --remove-hosts %s "
                 " -d %s -X -N -S default -r"
                 " /vertica.deb -L CE -Y --no-system-checks"
                 " --ignore-aws-instance-type"
                 " --ignore-install-config")
UPDATE_ADD = ("/opt/vertica/sbin/update_vertica --add-hosts %s "
              " -d %s -X -N -S default -r"
              " /vertica.deb -L CE -Y --no-system-checks"
              " --ignore-aws-instance-type"
              " --ignore-install-config")
USER_EXISTS = ("/opt/vertica/bin/vsql -w '%s' -c "
               "\"select 1 from users where user_name = '%s'\" "
               "| grep row | awk '{print $1}' | cut -c2-")
VERTICA_ADMIN = "dbadmin"
VERTICA_ADMIN_GRP = "verticadba"
VERTICA_AGENT_SERVICE_COMMAND = "service vertica_agent %s"
VERTICA_CONF = "/etc/vertica.cnf"
INSTALL_TIMEOUT = 1000
CREATE_LIBRARY = "CREATE LIBRARY %s AS '%s'"
CREATE_SOURCE = "CREATE SOURCE %s AS LANGUAGE '%s' NAME '%s' LIBRARY %s"
UDL_LIBS = [
    {
        'func_name': "curl",
        'lib_name': "curllib",
        'language': "C++",
        'factory': "CurlSourceFactory",
        'path': "/opt/vertica/sdk/examples/build/cURLLib.so"
    },
]


def shell_execute(command, command_executor="root"):
    # This method encapsulates utils.execute for 2 purpose:
    # 1. Helps in safe testing.
    # 2. Helps in executing commands as other user, using their environment.

    # Note: This method uses su because using sudo -i -u <user> <command>
    # does not works with vertica installer
    # and it has problems while executing remote commands.
    return utils.execute("sudo", "su", "-", command_executor, "-c", "%s"
                         % command)


class VSqlError(object):
    def __init__(self, stderr):
        """Parse the stderr part of the VSql output.
        stderr looks like: "ERROR 3117: Division by zero"
        :param stderr:  string from executing statement via vsql
        """
        parse = re.match(r"^(ERROR|WARNING) (\d+): (.+)$", stderr)
        if not parse:
            raise ValueError(_("VSql stderr %(msg)s not recognized.")
                             % {'msg': stderr})
        self.type = parse.group(1)
        self.code = int(parse.group(2))
        self.msg = parse.group(3)

    def is_warning(self):
        return bool(self.type == "WARNING")

    def __str__(self):
        return "Vertica %s (%s): %s" % (self.type, self.code, self.msg)


def exec_vsql_command(dbadmin_password, command):
    """Executes a VSQL command with the given dbadmin password."""
    out, err = shell_execute("/opt/vertica/bin/vsql -w \'%s\' -c \"%s\""
                             % (dbadmin_password, command),
                             VERTICA_ADMIN)
    if err:
        err = VSqlError(err)
    return out, err
