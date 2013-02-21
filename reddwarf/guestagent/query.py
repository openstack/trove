# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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
                 host=None, clear=None, hashed=None, grant_option=True):
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
    def _identity(self):
        if self.clear:
            return "IDENTIFIED BY '%s'" % self.clear
        if self.hashed:
            return "IDENTIFIED BY PASSWORD '%s'" % self.hashed
        return ""

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
        # User and host to be granted permission. Optionally, password, too.
        whom = [("TO %s" % self._user_host),
                self._identity,
                ]
        return " ".join(whom)

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
        # Optionally, password, too.
        whom = [("FROM %s" % self._user_host),
                self._identity,
                ]
        return " ".join(whom)


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
        #query = [("CREATE USER '%s'@'%s'" % (self.user, self._host)),
        query = ["CREATE USER :user@:host"]
        if self._identity:
            query.append(self._identity)
        return " ".join(query) + ";"


class UpdateUser(object):

    def __init__(self, user, host=None, clear=None):
        self.user = user
        self.host = host
        self.clear = clear

    def __repr__(self):
        return str(self)

    @property
    def _set_password(self):
        return "SET Password=PASSWORD('%s')" % self.clear

    @property
    def _host(self):
        if not self.host:
            return "%"
        return self.host

    @property
    def _where(self):
        clauses = []
        if self.user:
            clauses.append("User = '%s'" % self.user)
        if self.host:
            clauses.append("Host = '%s'" % self._host)
        if not clauses:
            return ""
        return "WHERE %s" % " AND ".join(clauses)

    def __str__(self):
        query = ["UPDATE mysql.user",
                 self._set_password,
                 self._where,
                 ]
        return " ".join(query) + ";"


class DropUser(object):

    def __init__(self, user):
        self.user = user

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "DROP USER `%s`;" % self.user


### Miscellaneous queries that need no parameters.

FLUSH = "FLUSH PRIVILEGES;"
ROOT_ENABLED = ("SELECT User FROM mysql.user "
                "WHERE User = 'root' AND host != 'localhost';")
REMOVE_ANON = "DELETE FROM mysql.user WHERE User = '';"
REMOVE_ROOT = ("DELETE FROM mysql.user "
               "WHERE User = 'root' AND Host != 'localhost';")
