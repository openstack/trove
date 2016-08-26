# Copyright (c) 2013 OpenStack Foundation
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

import psycopg2

from trove.common import exception

PG_ADMIN = 'os_admin'


class PostgresConnection(object):

    def __init__(self, autocommit=False, **connection_args):
        self._autocommit = autocommit
        self._connection_args = connection_args

    def execute(self, statement, identifiers=None, data_values=None):
        """Execute a non-returning statement.
        """
        self._execute_stmt(statement, identifiers, data_values, False)

    def query(self, query, identifiers=None, data_values=None):
        """Execute a query and return the result set.
        """
        return self._execute_stmt(query, identifiers, data_values, True)

    def _execute_stmt(self, statement, identifiers, data_values, fetch):
        if statement:
            with psycopg2.connect(**self._connection_args) as connection:
                connection.autocommit = self._autocommit
                with connection.cursor() as cursor:
                    cursor.execute(
                        self._bind(statement, identifiers), data_values)
                    if fetch:
                        return cursor.fetchall()
        else:
            raise exception.UnprocessableEntity(_("Invalid SQL statement: %s")
                                                % statement)

    def _bind(self, statement, identifiers):
        if identifiers:
            return statement.format(*identifiers)
        return statement


class PostgresLocalhostConnection(PostgresConnection):

    HOST = 'localhost'

    def __init__(self, user, password=None, port=5432, autocommit=False):
        super(PostgresLocalhostConnection, self).__init__(
            autocommit=autocommit, user=user, password=password,
            host=self.HOST, port=port)


# TODO(pmalik): No need to recreate the connection every time.
def psql(statement, timeout=30):
    """Execute a non-returning statement (usually DDL);
    Turn autocommit ON (this is necessary for statements that cannot run
    within an implicit transaction, like CREATE DATABASE).
    """
    return PostgresLocalhostConnection(
        PG_ADMIN, autocommit=True).execute(statement)


# TODO(pmalik): No need to recreate the connection every time.
def query(query, timeout=30):
    """Execute a query and return the result set.
    """
    return PostgresLocalhostConnection(
        PG_ADMIN, autocommit=False).query(query)


class DatabaseQuery(object):

    @classmethod
    def list(cls, ignore=()):
        """Query to list all databases."""

        statement = (
            "SELECT datname, pg_encoding_to_char(encoding), "
            "datcollate FROM pg_database "
            "WHERE datistemplate = false"
        )

        for name in ignore:
            statement += " AND datname != '{name}'".format(name=name)

        return statement

    @classmethod
    def create(cls, name, encoding=None, collation=None):
        """Query to create a database."""

        statement = "CREATE DATABASE \"{name}\"".format(name=name)
        if encoding is not None:
            statement += " ENCODING = '{encoding}'".format(
                encoding=encoding,
            )
        if collation is not None:
            statement += " LC_COLLATE = '{collation}'".format(
                collation=collation,
            )

        return statement

    @classmethod
    def drop(cls, name):
        """Query to drop a database."""

        return "DROP DATABASE IF EXISTS \"{name}\"".format(name=name)


class UserQuery(object):

    @classmethod
    def list(cls, ignore=()):
        """Query to list all users."""

        statement = (
            "SELECT usename, datname, pg_encoding_to_char(encoding), "
            "datcollate FROM pg_catalog.pg_user "
            "LEFT JOIN pg_catalog.pg_database "
            "ON CONCAT(usename, '=CTc/os_admin') = ANY(datacl::text[]) "
            "WHERE (datistemplate ISNULL OR datistemplate = false)")
        if ignore:
            for name in ignore:
                statement += " AND usename != '{name}'".format(name=name)

        return statement

    @classmethod
    def list_root(cls, ignore=()):
        """Query to list all superuser accounts."""

        statement = (
            "SELECT usename FROM pg_catalog.pg_user WHERE usesuper = true"
        )

        for name in ignore:
            statement += " AND usename != '{name}'".format(name=name)

        return statement

    @classmethod
    def get(cls, name):
        """Query to get a single user."""

        return cls.list() + " AND usename = '{name}'".format(name=name)

    @classmethod
    def create(cls, name, password, encrypt_password=None, *options):
        """Query to create a user with a password."""

        create_clause = "CREATE USER \"{name}\"".format(name=name)
        with_clause = cls._build_with_clause(
            password, encrypt_password, *options)
        return ''.join([create_clause, with_clause])

    @classmethod
    def _build_with_clause(cls, password, encrypt_password=None, *options):
        tokens = ['WITH']
        if password:
            # Do not specify the encryption option if 'encrypt_password'
            # is None. PostgreSQL will use the configuration default.
            if encrypt_password is True:
                tokens.append('ENCRYPTED')
            elif encrypt_password is False:
                tokens.append('UNENCRYPTED')
            tokens.append('PASSWORD')
            tokens.append("'{password}'".format(password=password))
        if options:
            tokens.extend(options)

        if len(tokens) > 1:
            return ' '.join(tokens)

        return ''

    @classmethod
    def update_password(cls, name, password, encrypt_password=None):
        """Query to update the password for a user."""

        return cls.alter_user(name, password, encrypt_password)

    @classmethod
    def alter_user(cls, name, password, encrypt_password=None, *options):
        """Query to alter a user."""

        alter_clause = "ALTER USER \"{name}\"".format(name=name)
        with_clause = cls._build_with_clause(
            password, encrypt_password, *options)
        return ''.join([alter_clause, with_clause])

    @classmethod
    def update_name(cls, old, new):
        """Query to update the name of a user.
        This statement also results in an automatic permission transfer to the
        new username.
        """

        return "ALTER USER \"{old}\" RENAME TO \"{new}\"".format(
            old=old,
            new=new,
        )

    @classmethod
    def drop(cls, name):
        """Query to drop a user."""

        return "DROP USER \"{name}\"".format(name=name)


class AccessQuery(object):

    @classmethod
    def grant(cls, user, database):
        """Query to grant user access to a database."""

        return "GRANT ALL ON DATABASE \"{database}\" TO \"{user}\"".format(
            database=database,
            user=user,
        )

    @classmethod
    def revoke(cls, user, database):
        """Query to revoke user access to a database."""

        return "REVOKE ALL ON DATABASE \"{database}\" FROM \"{user}\"".format(
            database=database,
            user=user,
        )
