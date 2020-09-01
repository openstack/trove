# Copyright 2020 Catalyst Cloud
#
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
        return f'DROP DATABASE IF EXISTS "{name}"'


class UserQuery(object):

    @classmethod
    def list(cls, ignore=()):
        """Query to list all users."""
        statement = (
            "SELECT usename, datname, pg_encoding_to_char(encoding), "
            "datcollate FROM pg_catalog.pg_user "
            "LEFT JOIN pg_catalog.pg_database "
            "ON CONCAT(usename, '=CTc/postgres') = ANY(datacl::text[]) "
            "WHERE (datistemplate ISNULL OR datistemplate = false)")
        if ignore:
            for name in ignore:
                statement += f" AND usename != '{name}'"

        return statement

    @classmethod
    def list_root(cls, ignore=()):
        """Query to list all superuser accounts."""
        statement = (
            "SELECT usename FROM pg_catalog.pg_user WHERE usesuper = true"
        )

        for name in ignore:
            statement += f" AND usename != '{name}'"

        return statement

    @classmethod
    def get(cls, name):
        """Query to get a single user."""
        return cls.list() + f" AND usename = '{name}'"

    @classmethod
    def create(cls, name, password, encrypt_password=None, *options):
        """Query to create a user with a password."""
        create_clause = "CREATE USER \"{name}\"".format(name=name)
        with_clause = cls._build_with_clause(
            password, encrypt_password, *options)
        return ' '.join([create_clause, with_clause])

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

        alter_clause = f'ALTER USER "{name}"'
        with_clause = cls._build_with_clause(
            password, encrypt_password, *options)
        return ''.join([alter_clause, with_clause])

    @classmethod
    def update_name(cls, old, new):
        """Query to update the name of a user.
        This statement also results in an automatic permission transfer to the
        new username.
        """
        return f'ALTER USER "{old}" RENAME TO "{new}"'

    @classmethod
    def drop(cls, name):
        """Query to drop a user."""
        return f'DROP USER IF EXISTS "{name}"'


class AccessQuery(object):

    @classmethod
    def grant(cls, user, database):
        """Query to grant user access to a database."""
        return f'GRANT ALL ON DATABASE "{database}" TO "{user}"'

    @classmethod
    def revoke(cls, user, database):
        """Query to revoke user access to a database."""
        return f'REVOKE ALL ON DATABASE "{database}" FROM "{user}"'
