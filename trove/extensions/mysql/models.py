# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack Foundation
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
Model classes that extend the instances functionality for MySQL instances.
"""

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.common.remote import create_guest_client
from trove.db import get_db_api
from trove.guestagent.db import models as guest_models
from trove.instance import models as base_models
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

CONF = cfg.CONF
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

    _data_fields = ['name', 'host', 'password', 'databases']

    def __init__(self, name, host, password, databases):
        self.name = name
        self.host = host
        self.password = password
        self.databases = databases

    @classmethod
    def load(cls, context, instance_id, username, hostname):
        load_and_verify(context, instance_id)
        validate = guest_models.MySQLUser()
        validate.name = username
        validate.host = hostname
        client = create_guest_client(context, instance_id)
        found_user = client.get_user(username=username, hostname=hostname)
        if not found_user:
            return None
        database_names = [{'name': db['_name']}
                          for db in found_user['_databases']]
        return cls(found_user['_name'],
                   found_user['_host'],
                   found_user['_password'],
                   database_names)

    @classmethod
    def create(cls, context, instance_id, users):
        # Load InstanceServiceStatus to verify if it's running
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        for user in users:
            user_name = user['_name']
            host_name = user['_host']
            if host_name is None:
                host_name = '%'
            userhost = "%s@%s" % (user_name, host_name)
            existing_users, _nadda = Users.load_with_client(
                client,
                limit=1,
                marker=userhost,
                include_marker=True)
            if (len(existing_users) > 0 and
                    str(existing_users[0].name) == str(user_name) and
                    str(existing_users[0].host) == str(host_name)):
                raise exception.UserAlreadyExists(name=user_name,
                                                  host=host_name)
        return client.create_user(users)

    @classmethod
    def delete(cls, context, instance_id, user):
        load_and_verify(context, instance_id)
        create_guest_client(context, instance_id).delete_user(user)

    @classmethod
    def access(cls, context, instance_id, username, hostname):
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        databases = client.list_access(username, hostname)
        dbs = []
        for db in databases:
            dbs.append(Schema(name=db['_name'],
                              collate=db['_collate'],
                              character_set=db['_character_set']))
        return UserAccess(dbs)

    @classmethod
    def grant(cls, context, instance_id, username, hostname, databases):
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        client.grant_access(username, hostname, databases)

    @classmethod
    def revoke(cls, context, instance_id, username, hostname, database):
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        client.revoke_access(username, hostname, database)

    @classmethod
    def change_password(cls, context, instance_id, users):
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        change_users = []
        for user in users:
            change_user = {'name': user.name,
                           'host': user.host,
                           'password': user.password,
                           }
            change_users.append(change_user)
        client.change_passwords(change_users)

    @classmethod
    def update_attributes(cls, context, instance_id, username, hostname,
                          user_attrs):
        load_and_verify(context, instance_id)
        client = create_guest_client(context, instance_id)
        user_name = user_attrs.get('name')
        host_name = user_attrs.get('host')
        user = user_name or username
        host = host_name or hostname
        userhost = "%s@%s" % (user, host)
        if user_name or host_name:
            existing_users, _nadda = Users.load_with_client(
                client,
                limit=1,
                marker=userhost,
                include_marker=True)
            if (len(existing_users) > 0 and
                    existing_users[0].name == user and
                    existing_users[0].host == host):
                raise exception.UserAlreadyExists(name=user,
                                                  host=host)
        client.update_attributes(username, hostname, user_attrs)


class UserAccess(object):
    _data_fields = ['databases']

    def __init__(self, databases):
        self.databases = databases


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
        RootHistory.create(context, instance_id, user)
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
        LOG.debug(_("Saving %(name)s: %(dict)s") %
                  {'name': self.__class__.__name__, 'dict': self.__dict__})
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
        return history.save()


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

    DEFAULT_LIMIT = CONF.users_page_size

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
        ignore_users = CONF.ignore_users
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
                                    mysql_user.host,
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

    DEFAULT_LIMIT = CONF.databases_page_size

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
        ignore_dbs = CONF.ignore_dbs
        for schema in schemas:
            mysql_schema = guest_models.MySQLDatabase()
            mysql_schema.deserialize(schema)
            if mysql_schema.name in ignore_dbs:
                continue
            model_schemas.append(Schema(mysql_schema.name,
                                        mysql_schema.collate,
                                        mysql_schema.character_set))
        return model_schemas, next_marker
