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

import os
import tempfile
import uuid

from trove.common import utils
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


def execute(*command, **kwargs):
    """Execute a command as the 'postgres' user."""

    LOG.debug('Running as postgres: {0}'.format(command))
    return utils.execute_with_timeout(
        "sudo", "-u", "postgres", *command, **kwargs
    )


def result(filename):
    """A generator representing the results of a query.

    This generator produces result records of a query by iterating over a
    CSV file created by the query. When the file is out of records it is
    removed.

    The purpose behind this abstraction is to provide a record set interface
    with minimal memory consumption without requiring an active DB connection.
    This makes it possible to iterate over any sized record set without
    allocating memory for the entire record set and without using a DB cursor.

    Each row is returned as an iterable of column values. The order of these
    values is determined by the query.
    """

    utils.execute_with_timeout(
        'sudo', 'chmod', '777', filename,
    )
    with open(filename, 'r+') as file_handle:
        for line in file_handle:
            if line != "":
                yield line.split(',')
    execute(
        "rm", "{filename}".format(filename=filename),
    )
    raise StopIteration()


def psql(statement, timeout=30):
    """Execute a statement using the psql client."""

    LOG.debug('Sending to local db: {0}'.format(statement))
    return execute('psql', '-c', statement, timeout=timeout)


def query(statement, timeout=30):
    """Execute a pgsql query and get a generator of results.

    This method will pipe a CSV format of the query results into a temporary
    file. The return value is a generator object that feeds from this file.
    """

    filename = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    LOG.debug('Querying: {0}'.format(statement))
    psql(
        "Copy ({statement}) To '{filename}' With CSV".format(
            statement=statement,
            filename=filename,
        ),
        timeout=timeout,
    )

    return result(filename)


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

        statement = "SELECT usename FROM pg_catalog.pg_user"
        if ignore:
            # User a simple tautology so all clauses can be AND'ed without
            # crazy special logic.
            statement += " WHERE 1=1"
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

        return (
            "SELECT usename FROM pg_catalog.pg_user "
            "WHERE usename = '{name}'".format(name=name)
        )

    @classmethod
    def create(cls, name, password):
        """Query to create a user with a password."""

        return "CREATE USER \"{name}\" WITH PASSWORD '{password}'".format(
            name=name,
            password=password,
        )

    @classmethod
    def update_password(cls, name, password):
        """Query to update the password for a user."""

        return "ALTER USER \"{name}\" WITH PASSWORD '{password}'".format(
            name=name,
            password=password,
        )

    @classmethod
    def update_name(cls, old, new):
        """Query to update the name of a user."""

        return "ALTER USER \"{old}\" RENAME TO '{new}'".format(
            old=old,
            new=new,
        )

    @classmethod
    def drop(cls, name):
        """Query to drop a user."""

        return "DROP USER \"{name}\"".format(name=name)


class AccessQuery(object):

    @classmethod
    def list(cls, user):
        """Query to list grants for a user."""

        return (
            "SELECT datname "
            "FROM pg_database "
            "WHERE datistemplate = false "
            "AND 'user {user}=CTc' = ANY (datacl)".format(user=user)
        )

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
