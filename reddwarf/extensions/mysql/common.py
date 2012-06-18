#    Copyright 2012 OpenStack LLC
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

from reddwarf.common import exception
from reddwarf.guestagent.db import models as guest_models


def populate_databases(dbs):
    """
    Create a serializable request with user provided data
    for creating new databases.
    """
    try:
        databases = []
        for database in dbs:
            mydb = guest_models.MySQLDatabase()
            mydb.name = database.get('name', '')
            mydb.character_set = database.get('character_set', '')
            mydb.collate = database.get('collate', '')
            databases.append(mydb.serialize())
        return databases
    except ValueError as ve:
        raise exception.BadRequest(ve.message)


def populate_users(users):
    """Create a serializable request containing users"""
    try:
        users_data = []
        for user in users:
            u = guest_models.MySQLUser()
            u.name = user.get('name', '')
            u.password = user.get('password', '')
            dbs = user.get('databases', '')
            if dbs:
                for db in dbs:
                    u.databases = db.get('name', '')
            users_data.append(u.serialize())
        return users_data
    except ValueError as ve:
        raise exception.BadRequest(ve.message)
