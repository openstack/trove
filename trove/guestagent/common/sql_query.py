# Copyright (c) 2011 OpenStack Foundation
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

"""

Intermediary class for building SQL queries for use by the guest agent.
Do not hard-code strings into the guest agent; use this module to build
them for you.

"""
import semantic_version


class Query(object):

    def __init__(self, columns=None, tables=None, where=None, order=None,
                 group=None, limit=None):
        self.columns = columns or []
        self.tables = tables or []
        self.where = where or []
        self.order = order or []
        self.group = group or []
        self.limit = limit

    def __repr__(self):
        return str(self)

    @property
    def _columns(self):
        if not self.columns:
            return "SELECT *"
        return "SELECT %s" % (", ".join(self.columns))

    @property
    def _tables(self):
        return "FROM %s" % (", ".join(self.tables))

    @property
    def _where(self):
        if not self.where:
            return ""
        return "WHERE %s" % (" AND ".join(self.where))

    @property
    def _order(self):
        if not self.order:
            return ""
        return "ORDER BY %s" % (", ".join(self.order))

    @property
    def _group_by(self):
        if not self.group:
            return ""
        return "GROUP BY %s" % (", ".join(self.group))

    @property
    def _limit(self):
        if not self.limit:
            return ""
        return "LIMIT %s" % str(self.limit)

    def __str__(self):
        query = [
            self._columns,
            self._tables,
            self._where,
            self._order,
            self._group_by,
            self._limit,
        ]
        query = [q for q in query if q]
        return " ".join(query) + ";"


class Grant(object):

    PERMISSIONS = ["ALL",
                   "ALL PRIVILEGES",
                   "ALTER ROUTINE",
                   "ALTER",
                   "CREATE ROUTINE",
                   "CREATE TEMPORARY TABLES",
                   "CREATE USER",
                   "CREATE VIEW",
                   "CREATE",
                   "DELETE",
                   "DROP",
                   "EVENT",
                   "EXECUTE",
                   "FILE",
                   "INDEX",
                   "INSERT",
                   "LOCK TABLES",
                   "PROCESS",
                   "REFERENCES",
                   "RELOAD",
                   "REPLICATION CLIENT",
                   "REPLICATION SLAVE",
                   "SELECT",
                   "SHOW DATABASES",
                   "SHOW VIEW",
                   "SHUTDOWN",
                   "SUPER",
                   "TRIGGER",
                   "UPDATE",
                   "USAGE",
                   ]

    def __init__(self, permissions=None, database=None, table=None, user=None,
                 host=None, clear=None, hashed=None, grant_option=False):
        self.permissions = permissions or []
        self.database = database
        self.table = table
        self.user = user
        self.host = host
        self.clear = clear
        self.hashed = hashed
        self.grant_option = grant_option

    def __repr__(self):
        return str(self)

    @property
    def _permissions(self):
        if not self.permissions:
            return "USAGE"
        if "ALL" in self.permissions:
            return "ALL PRIVILEGES"
        if "ALL PRIVILEGES" in self.permissions:
            return "ALL PRIVILEGES"
        filtered = [perm for perm in set(self.permissions)
                    if perm in self.PERMISSIONS]
        return ", ".join(sorted(filtered))

    @property
    def _database(self):
        if not self.database:
            return "*"
        return "`%s`" % self.database

    @property
    def _table(self):
        if self.table:
            return "'%s'" % self.table
        return "*"

    @property
    def _user(self):
        return self.user or ""

    @property
    def _host(self):
        return self.host or "%"

    @property
    def _user_host(self):
        return "`%s`@`%s`" % (self._user, self._host)

    @property
    def _what(self):
        # Permissions to be granted to the user.
        return "GRANT %s" % self._permissions

    @property
    def _where(self):
        # Database and table to which the user is granted permissions.
        return "ON %s.%s" % (self._database, self._table)

    @property
    def _whom(self):
        return f"TO {self._user_host}"

    @property
    def _with(self):
        clauses = []

        if self.grant_option:
            clauses.append("GRANT OPTION")

        if not clauses:
            return ""

        return "WITH %s" % ", ".join(clauses)

    def __str__(self):
        query = [self._what,
                 self._where,
                 self._whom,
                 self._with,
                 ]
        query = [q for q in query if q]
        return " ".join(query) + ";"


class Revoke(Grant):

    def __init__(self, permissions=None, database=None, table=None, user=None,
                 host=None, clear=None, hashed=None):
        self.permissions = permissions or []
        self.database = database
        self.table = table
        self.user = user
        self.host = host
        self.clear = clear
        self.hashed = hashed

    def __str__(self):
        query = [self._what,
                 self._where,
                 self._whom,
                 ]
        query = [q for q in query if q]
        return " ".join(query) + ";"

    @property
    def _permissions(self):
        if not self.permissions:
            return "ALL"
        if "ALL" in self.permissions:
            return "ALL"
        if "ALL PRIVILEGES" in self.permissions:
            return "ALL"
        filtered = [perm for perm in self.permissions
                    if perm in self.PERMISSIONS]
        return ", ".join(sorted(filtered))

    @property
    def _what(self):
        # Permissions to be revoked from the user.
        return "REVOKE %s" % self._permissions

    @property
    def _whom(self):
        # User and host from whom to revoke permission.
        return f"FROM {self._user_host}"


class CreateDatabase(object):

    def __init__(self, database, charset=None, collate=None):
        self.database = database
        self.charset = charset
        self.collate = collate

    def __repr__(self):
        return str(self)

    @property
    def _charset(self):
        if not self.charset:
            return ""
        return "CHARACTER SET = '%s'" % self.charset

    @property
    def _collate(self):
        if not self.collate:
            return ""
        return "COLLATE = '%s'" % self.collate

    def __str__(self):
        query = [("CREATE DATABASE IF NOT EXISTS `%s`" % self.database),
                 self._charset,
                 self._collate,
                 ]
        query = [q for q in query if q]
        return " ".join(query) + ";"


class DropDatabase(object):

    def __init__(self, database):
        self.database = database

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "DROP DATABASE `%s`;" % self.database


class CreateUser(object):

    def __init__(self, user, host=None, clear=None, hashed=None):
        self.user = user
        self.host = host
        self.clear = clear  # A clear password
        self.hashed = hashed  # A hashed password

    def __repr__(self):
        return str(self)

    @property
    def keyArgs(self):
        return {'user': self.user,
                'host': self._host,
                }

    @property
    def _host(self):
        if not self.host:
            return "%"
        return self.host

    @property
    def _identity(self):
        if self.clear:
            return "IDENTIFIED BY '%s'" % self.clear
        if self.hashed:
            return "IDENTIFIED BY PASSWORD '%s'" % self.hashed
        return ""

    def __str__(self):
        query = ["CREATE USER :user@:host",
                 self._identity,
                 ]
        query = [q for q in query if q]
        return " ".join(query) + ";"


class RenameUser(object):

    def __init__(self, user, host=None, new_user=None,
                 new_host=None):
        self.user = user
        self.host = host or '%'
        self.new_user = new_user
        self.new_host = new_host

    def __repr__(self):
        return str(self)

    def __str__(self):
        properties = {'old_name': self.user,
                      'old_host': self.host,
                      'new_name': self.new_user or self.user,
                      'new_host': self.new_host or self.host}
        return ("RENAME USER '%(old_name)s'@'%(old_host)s' TO "
                "'%(new_name)s'@'%(new_host)s';" % properties)


class SetPassword(object):
    def __init__(self, user, host=None, new_password=None, ds=None,
                 ds_version=None):
        self.user = user
        self.host = host or '%'
        self.new_password = new_password or ''
        self.ds = ds or 'mysql'
        self.ds_version = ds_version or '5.7'

    def __repr__(self):
        return str(self)

    def __str__(self):
        if self.ds == 'mysql':
            cur_version = semantic_version.Version.coerce(self.ds_version)
            mysql_575 = semantic_version.Version('5.7.5')
            if cur_version <= mysql_575:
                return (f"SET PASSWORD FOR '{self.user}'@'{self.host}' = "
                        f"PASSWORD('{self.new_password}');")

            return (f"ALTER USER '{self.user}'@'{self.host}' "
                    f"IDENTIFIED WITH mysql_native_password "
                    f"BY '{self.new_password}';")
        elif self.ds == 'mariadb':
            return (f"ALTER USER '{self.user}'@'{self.host}' IDENTIFIED VIA "
                    f"mysql_native_password USING "
                    f"PASSWORD('{self.new_password}');")


class DropUser(object):

    def __init__(self, user, host='%'):
        self.user = user
        self.host = host

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "DROP USER `%s`@`%s`;" % (self.user, self.host)


class SetServerVariable(object):

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __repr__(self):
        return str(self)

    def __str__(self):
        if self.value is True:
            return "SET GLOBAL %s=%s" % (self.key, 1)
        elif self.value is False:
            return "SET GLOBAL %s=%s" % (self.key, 0)
        elif self.value is None:
            return "SET GLOBAL %s" % (self.key)
        elif isinstance(self.value, str):
            return "SET GLOBAL %s='%s'" % (self.key, self.value)
        else:
            return "SET GLOBAL %s=%s" % (self.key, self.value)


# Miscellaneous queries that need no parameters.
FLUSH = "FLUSH PRIVILEGES;"
ROOT_ENABLED = ("SELECT User FROM mysql.user "
                "WHERE User = 'root' AND Host != 'localhost';")
REMOVE_ANON = "DELETE FROM mysql.user WHERE User = '';"
REMOVE_ROOT = ("DELETE FROM mysql.user "
               "WHERE User = 'root' AND Host != 'localhost';")
