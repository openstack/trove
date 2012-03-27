# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Model classes that form the core of instances functionality."""

import logging

from reddwarf import db

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.guestagent.db import models as guest_models
from reddwarf.guestagent import api as guest_api

CONFIG = config.Config
LOG = logging.getLogger(__name__)


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


class User(object):

    _data_fields = ['name', 'password', 'databases']

    def __init__(self, name, password, databases):
        self.name = name
        self.password = password
        self.databases = databases

    @classmethod
    def create(cls, context, instance_id, users):
        guest_api.API().create_user(context, instance_id, users)

    @classmethod
    def delete(cls, context, instance_id, username):
        guest_api.API().delete_user(context, instance_id, username)


class Users(object):

    @classmethod
    def load(cls, context, instance_id):
        user_list = guest_api.API().list_users(context, instance_id)
        model_users = []
        for user in user_list:
            mysql_user = guest_models.MySQLUser()
            mysql_user.deserialize(user)
            # TODO(hub-cap): databases are not being returned in the
            # reference agent
            dbs = []
            for db in mysql_user.databases:
                dbs.append({'name': db['_name']})
            model_users.append(User(mysql_user.name,
                                    mysql_user.password,
                                    dbs))
        return model_users


class Schema(object):

    _data_fields = ['name', 'collate', 'character_set']

    def __init__(self, name, collate, character_set):
        self.name = name
        self.collate = collate
        self.character_set = character_set

    @classmethod
    def create(cls, context, instance_id, schemas):
        guest_api.API().create_database(context, instance_id, schemas)

    @classmethod
    def delete(cls, context, instance_id, schema):
        guest_api.API().delete_database(context, instance_id, schema)


class Schemas(object):

    @classmethod
    def load(cls, context, instance_id):
        schema_list = guest_api.API().list_databases(context, instance_id)
        model_schemas = []
        for schema in schema_list:
            mysql_schema = guest_models.MySQLDatabase()
            mysql_schema.deserialize(schema)
            model_schemas.append(Schema(mysql_schema.name,
                                        mysql_schema.collate,
                                        mysql_schema.character_set))
        return model_schemas
