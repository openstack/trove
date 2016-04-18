#    Copyright 2012 OpenStack Foundation
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

from six.moves.urllib.parse import unquote

from trove.common import exception
from trove.guestagent.db import models as guest_models


def populate_validated_databases(dbs):
    """
    Create a serializable request with user provided data
    for creating new databases.
    """
    try:
        databases = []
        unique_identities = set()
        for database in dbs:
            mydb = guest_models.ValidatedMySQLDatabase()
            mydb.name = database.get('name', '')
            if mydb.name in unique_identities:
                raise exception.DatabaseInitialDatabaseDuplicateError()
            unique_identities.add(mydb.name)
            mydb.character_set = database.get('character_set', '')
            mydb.collate = database.get('collate', '')
            databases.append(mydb.serialize())
        return databases
    except ValueError as ve:
        # str(ve) contains user input and may include '%' which can cause a
        # format str vulnerability. Escape the '%' to avoid this. This is
        # okay to do since we're not using dict args here in any case.
        safe_string = str(ve).replace('%', '%%')
        raise exception.BadRequest(safe_string)


def populate_users(users, initial_databases=None):
    """Create a serializable request containing users."""
    users_data = []
    unique_identities = set()
    for user in users:
        u = guest_models.MySQLUser()
        u.name = user.get('name', '')
        u.host = user.get('host', '%')
        user_identity = (u.name, u.host)
        if user_identity in unique_identities:
            raise exception.DatabaseInitialUserDuplicateError()
        unique_identities.add(user_identity)
        u.password = user.get('password', '')
        user_dbs = user.get('databases', '')
        # user_db_names guaranteed unique and non-empty by apischema
        user_db_names = [user_db.get('name', '') for user_db in user_dbs]
        for user_db_name in user_db_names:
            if (initial_databases is not None and user_db_name not in
                    initial_databases):
                raise exception.DatabaseForUserNotInDatabaseListError(
                    user=u.name, database=user_db_name)
            u.databases = user_db_name
        users_data.append(u.serialize())
    return users_data


def unquote_user_host(user_hostname):
    unquoted = unquote(user_hostname)
    if '@' not in unquoted:
        return unquoted, '%'
    if unquoted.endswith('@'):
        return unquoted, '%'
    splitup = unquoted.split('@')
    host = splitup[-1]
    user = '@'.join(splitup[:-1])
    return user, host
