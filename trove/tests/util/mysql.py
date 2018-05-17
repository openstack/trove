# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

import re

from oslo_db.sqlalchemy import session
import pexpect
from sqlalchemy.exc import OperationalError
try:
    from sqlalchemy.exc import ResourceClosedError
except ImportError:
    ResourceClosedError = Exception

from trove import tests
from trove.tests.config import CONFIG


def create_mysql_connection(host, user, password):
    connection = CONFIG.mysql_connection_method
    if connection['type'] == "direct":
        return SqlAlchemyConnection(host, user, password)
    elif connection['type'] == "tunnel":
        if 'ssh' not in connection:
            raise RuntimeError("If connection type is 'tunnel' then a "
                               "property 'ssh' is expected.")
        return PexpectMySqlConnection(connection['ssh'], host, user, password)
    else:
        raise RuntimeError("Unknown Bad test configuration for "
                           "mysql_connection_method")


class MySqlConnectionFailure(RuntimeError):

    def __init__(self, msg):
        super(MySqlConnectionFailure, self).__init__(msg)


class MySqlPermissionsFailure(RuntimeError):

    def __init__(self, msg):
        super(MySqlPermissionsFailure, self).__init__(msg)


class SqlAlchemyConnection(object):

    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        try:
            self.engine = self._init_engine(user, password, host)
        except OperationalError as oe:
            if self._exception_is_permissions_issue(str(oe)):
                raise MySqlPermissionsFailure(oe)
            else:
                raise MySqlConnectionFailure(oe)

    @staticmethod
    def _exception_is_permissions_issue(msg):
        """Assert message cited a permissions issue and not something else."""
        pos_error = re.compile(r".*Host '[\w\.]*' is not allowed to connect "
                               "to this MySQL server.*")
        pos_error1 = re.compile(".*Access denied for user "
                                r"'[\w\*\!\@\#\^\&]*'@'[\w\.]*'.*")
        if (pos_error.match(msg) or pos_error1.match(msg)):
            return True

    def __enter__(self):
        try:
            self.conn = self.engine.connect()
        except OperationalError as oe:
            if self._exception_is_permissions_issue(str(oe)):
                raise MySqlPermissionsFailure(oe)
            else:
                raise MySqlConnectionFailure(oe)
        self.trans = self.conn.begin()
        return self

    def execute(self, cmd):
        """Execute some code."""
        cmd = cmd.replace("%", "%%")
        try:
            return self.conn.execute(cmd).fetchall()
        except Exception:
            self.trans.rollback()
            self.trans = None
            try:
                raise
            except ResourceClosedError:
                return []

    def __exit__(self, type, value, traceback):
        if self.trans:
            if type is not None:  # An error occurred
                self.trans.rollback()
            else:
                self.trans.commit()
        self.conn.close()

    @staticmethod
    def _init_engine(user, password, host):
        return session.EngineFacade(
            "mysql+pymysql://%s:%s@%s:3306" % (user, password, host)
        ).get_engine()


class PexpectMySqlConnection(object):

    TIME_OUT = 30

    def __init__(self, ssh_args, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        cmd = '%s %s' % (tests.SSH_CMD, ssh_args)
        self.proc = pexpect.spawn(cmd)
        print(cmd)
        self.proc.expect(r":~\$", timeout=self.TIME_OUT)
        cmd2 = "mysql --host '%s' -u '%s' '-p%s'\n" % \
               (self.host, self.user, self.password)
        print(cmd2)
        self.proc.send(cmd2)
        result = self.proc.expect([
            'mysql>',
            'Access denied',
            "Can't connect to MySQL server"],
            timeout=self.TIME_OUT)
        if result == 1:
            raise MySqlPermissionsFailure(self.proc.before)
        elif result == 2:
            raise MySqlConnectionFailure(self.proc.before)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.proc.close()

    def execute(self, cmd):
        self.proc.send(cmd + "\\G\n")
        outcome = self.proc.expect(['Empty set', 'mysql>'],
                                   timeout=self.TIME_OUT)
        if outcome == 0:
            return []
        else:
            # This next line might be invaluable for long test runs.
            print("Interpreting output: %s" % self.proc.before)
            lines = self.proc.before.split("\r\n")
            result = []
            row = None
            for line in lines:
                plural_s = "s" if len(result) != 0 else ""
                end_line = "%d row%s in set" % ((len(result) + 1), plural_s)
                if len(result) == 0:
                    end_line = "1 row in set"
                if (line.startswith("***************************") or
                        line.startswith(end_line)):
                    if row is not None:
                        result.append(row)
                    row = {}
                elif row is not None:
                    colon = line.find(": ")
                    field = line[:colon]
                    value = line[colon + 2:]
                    row[field] = value
            return result
