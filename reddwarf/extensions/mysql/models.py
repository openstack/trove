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

"""
Model classes that extend the instances functionality for MySQL instances.
"""

import logging

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.db import get_db_api
from reddwarf.instance import models as base_models
from reddwarf.guestagent.db import models as guest_models
from reddwarf.common.remote import create_guest_client

CONFIG = config.Config
LOG = logging.getLogger(__name__)


def persisted_models():
    return {'root_enabled_history': RootHistory}


def load_and_verify(context, instance_id):
    # Load InstanceServiceStatus to verify if its running
    instance = base_models.Instance.load(context, instance_id)
    if not instance.is_sql_running:
        raise exception.UnprocessableEntity(
            "Instance %s is not ready." % instance.id)
    else:
        return instance


class User(object):

    _data_fields = ['name', 'password', 'databases']

    def __init__(self, name, password, databases):
        self.name = name
        self.password = password
        self.databases = databases

    @classmethod
    def create(cls, context, instance_id, users):
        # Load InstanceServiceStatus to verify if it's running
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        for user in users:
            user_name = user['_name']
            existing_users, _nadda = Users.load_with_client(
                client,
                limit=1,
                marker=user_name,
                include_marker=True)
            if (len(existing_users) > 0 and
                    str(existing_users[0].name) == str(user_name)):
                raise exception.UserAlreadyExists(name=user_name)
        return client.create_user(users)

    @classmethod
    def delete(cls, context, instance_id, username):
        load_and_verify(context, instance_id)
        create_guest_client(context, instance_id).delete_user(username)


class Root(object):

    @classmethod
    def load(cls, context, instance_id):
        load_and_verify(context, instance_id)
        # TODO(pdmars): remove the is_root_enabled call from the guest agent,
        # just check the database for this information.
        # If the root history returns null or raises an exception, the root
        # user hasn't been enabled.
        try:
            root_history = RootHistory.load(context, instance_id)
        except exception.NotFound:
            return False
        if not root_history:
            return False
        return True

    @classmethod
    def create(cls, context, instance_id, user):
        load_and_verify(context, instance_id)
        root = create_guest_client(context, instance_id).enable_root()
        root_user = guest_models.RootUser()
        root_user.deserialize(root)
        root_history = RootHistory.create(context, instance_id, user)
        return root_user


class RootHistory(object):

    _auto_generated_attrs = ['id']
    _data_fields = ['instance_id', 'user', 'created']
    _table_name = 'root_enabled_history'

    def __init__(self, instance_id, user):
        self.id = instance_id
        self.user = user
        self.created = utils.utcnow()

    def save(self):
        LOG.debug(_("Saving %s: %s") % (self.__class__.__name__,
                                        self.__dict__))
        return get_db_api().save(self)

    @classmethod
    def load(cls, context, instance_id):
        history = get_db_api().find_by(cls, id=instance_id)
        return history

    @classmethod
    def create(cls, context, instance_id, user):
        history = cls.load(context, instance_id)
        if history is not None:
            return history
        history = RootHistory(instance_id, user)
        history.save()
        return history


def load_via_context(cls, context, instance_id):
    """Creates guest and fetches pagination arguments from the context."""
    load_and_verify(context, instance_id)
    limit = int(context.limit or cls.DEFAULT_LIMIT)
    limit = cls.DEFAULT_LIMIT if limit > cls.DEFAULT_LIMIT else limit
    client = create_guest_client(context, instance_id)
    # The REST API standard dictates that we *NEVER* include the marker.
    return cls.load_with_client(client=client, limit=limit,
                                marker=context.marker, include_marker=False)


class Users(object):

    DEFAULT_LIMIT = int(CONFIG.get('users_page_size', '20'))

    @classmethod
    def load(cls, context, instance_id):
        return load_via_context(cls, context, instance_id)

    @classmethod
    def load_with_client(cls, client, limit, marker, include_marker):
        user_list, next_marker = client.list_users(
            limit=limit,
            marker=marker,
            include_marker=include_marker)
        model_users = []
        ignore_users = CONFIG.get_list('ignore_users', [])
        for user in user_list:
            mysql_user = guest_models.MySQLUser()
            mysql_user.deserialize(user)
            if mysql_user.name in ignore_users:
                continue
            # TODO(hub-cap): databases are not being returned in the
            # reference agent
            dbs = []
            for db in mysql_user.databases:
                dbs.append({'name': db['_name']})
            model_users.append(User(mysql_user.name,
                                    mysql_user.password,
                                    dbs))
        return model_users, next_marker


class Schema(object):

    _data_fields = ['name', 'collate', 'character_set']

    def __init__(self, name, collate, character_set):
        self.name = name
        self.collate = collate
        self.character_set = character_set

    @classmethod
    def create(cls, context, instance_id, schemas):
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        for schema in schemas:
            schema_name = schema['_name']
            existing_schema, _nadda = Schemas.load_with_client(
                client,
                limit=1,
                marker=schema_name,
                include_marker=True)
            if (len(existing_schema) > 0 and
                    str(existing_schema[0].name) == str(schema_name)):
                raise exception.DatabaseAlreadyExists(name=schema_name)
        return client.create_database(schemas)

    @classmethod
    def delete(cls, context, instance_id, schema):
        load_and_verify(context, instance_id)
        create_guest_client(context, instance_id).delete_database(schema)


class Schemas(object):

    DEFAULT_LIMIT = int(CONFIG.get('databases_page_size', '20'))

    @classmethod
    def load(cls, context, instance_id):
        return load_via_context(cls, context, instance_id)

    @classmethod
    def load_with_client(cls, client, limit, marker, include_marker):
        schemas, next_marker = client.list_databases(
            limit=limit,
            marker=marker,
            include_marker=include_marker)
        model_schemas = []
        ignore_dbs = CONFIG.get_list('ignore_dbs', [])
        for schema in schemas:
            mysql_schema = guest_models.MySQLDatabase()
            mysql_schema.deserialize(schema)
            if mysql_schema.name in ignore_dbs:
                continue
            model_schemas.append(Schema(mysql_schema.name,
                                        mysql_schema.collate,
                                        mysql_schema.character_set))
        return model_schemas, next_marker
