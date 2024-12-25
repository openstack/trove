# Copyright [2015] Hewlett-Packard Development Company, L.P.
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

from oslo_log import log as logging

from trove.common.clients import create_guest_client
from trove.common.db import models as guest_models
from trove.common import exception
from trove.common import timeutils
from trove.db import get_db_api
from trove.instance import models as base_models

from trove.common import cfg
from trove.common.notification import StartNotification
from trove.common import utils

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def load_and_verify(context, instance_id,
                    enabled_datastore=['mysql', 'mariadb', 'postgresql']):
    """Check instance datastore.

    Some API operations are only supported for some specific datastores.
    """
    instance = base_models.Instance.load(context, instance_id)

    if instance.datastore_version.manager not in enabled_datastore:
        raise exception.UnprocessableEntity(
            "Operation not supported for datastore "
            f"{instance.datastore_version.manager}."
        )

    if not instance.is_datastore_running:
        raise exception.UnprocessableEntity(
            "Instance %s is not ready, status: %s." %
            (instance.id, instance.datastore_status.status)
        )

    return instance


class Root(object):

    @classmethod
    def load(cls, context, instance_id):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
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
    def create(cls, context, instance_id, root_password,
               cluster_instances_list=None):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        if root_password:
            root = create_guest_client(context,
                                       instance_id).enable_root_with_password(
                root_password)
        else:
            root = create_guest_client(context, instance_id).enable_root()

        root_user = guest_models.DatastoreUser.deserialize(root,
                                                           verify=False)
        root_user.make_root()

        # if cluster_instances_list none, then root create is called for
        # single instance, adding an RootHistory entry for the instance_id
        if cluster_instances_list is None:
            RootHistory.create(context, instance_id)

        return root_user

    @classmethod
    def delete(cls, context, instance_id):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        create_guest_client(context, instance_id).disable_root()


class ClusterRoot(Root):

    @classmethod
    def create(cls, context, instance_id, root_password,
               cluster_instances_list=None):
        root_user = super(ClusterRoot, cls).create(context, instance_id,
                                                   root_password,
                                                   cluster_instances_list=None)

        if cluster_instances_list:
            for instance in cluster_instances_list:
                RootHistory.create(context, instance)

        return root_user


class RootHistory(object):

    _auto_generated_attrs = ['id']
    _data_fields = ['instance_id', 'user', 'created']
    _table_name = 'root_enabled_history'

    def __init__(self, instance_id, user):
        self.id = instance_id
        self.user = user
        self.created = timeutils.utcnow()

    def save(self):
        LOG.debug("Saving %(name)s: %(dict)s",
                  {'name': self.__class__.__name__, 'dict': self.__dict__})
        return get_db_api().save(self)

    @classmethod
    def load(cls, context, instance_id):
        history = get_db_api().find_by(cls, id=instance_id)
        return history

    @classmethod
    def create(cls, context, instance_id):
        history = cls.load(context, instance_id)
        if history is not None:
            return history
        history = RootHistory(instance_id, context.user_id)
        return history.save()


def load_via_context(cls, context, instance_id):
    """Creates guest and fetches pagination arguments from the context."""
    load_and_verify(context, instance_id,
                    enabled_datastore=['mysql', 'mariadb', 'postgresql'])
    limit = utils.pagination_limit(context.limit, cls.DEFAULT_LIMIT)
    client = create_guest_client(context, instance_id)
    # The REST API standard dictates that we *NEVER* include the marker.
    return cls.load_with_client(client=client, limit=limit,
                                marker=context.marker, include_marker=False)


def persisted_models():
    return {'root_enabled_history': RootHistory}


class User(object):

    _data_fields = ['name', 'host', 'password', 'databases']

    def __init__(self, name, host, password, databases):
        self.name = name
        self.host = host
        self.password = password
        self.databases = databases

    @classmethod
    def load(cls, context, instance_id, username, hostname, root_user=False):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        validate = guest_models.DatastoreUser(name=username, host=hostname)
        if root_user:
            validate.make_root()
        validate.check_reserved()
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
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        client = create_guest_client(context, instance_id)
        for user in users:
            user_name = user['_name']
            host_name = user['_host']
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
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])

        with StartNotification(context, instance_id=instance_id,
                               username=user):
            create_guest_client(context, instance_id).delete_user(user)

    @classmethod
    def access(cls, context, instance_id, username, hostname):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
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
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        client = create_guest_client(context, instance_id)
        client.grant_access(username, hostname, databases)

    @classmethod
    def revoke(cls, context, instance_id, username, hostname, database):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        client = create_guest_client(context, instance_id)
        client.revoke_access(username, hostname, database)

    @classmethod
    def change_password(cls, context, instance_id, users):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
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

        user_changed = user_attrs.get('name')
        host_changed = user_attrs.get('host')

        user = user_changed or username
        host = host_changed or hostname

        validate = guest_models.DatastoreUser(name=user, host=host)
        validate.check_reserved()

        userhost = "%s@%s" % (user, host)
        if user_changed or host_changed:
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
        for user in user_list:
            guest_user = guest_models.DatastoreUser.deserialize(user,
                                                                verify=False)
            if guest_user.name in cfg.get_ignored_users():
                continue
            # TODO(hub-cap): databases are not being returned in the
            # reference agent
            dbs = []
            for db in guest_user.databases:
                dbs.append({'name': db['_name']})
            model_users.append(User(guest_user.name,
                                    guest_user.host,
                                    guest_user.password,
                                    dbs))
        return model_users, next_marker


class UserAccess(object):
    _data_fields = ['databases']

    def __init__(self, databases):
        self.databases = databases


class Schema(object):

    _data_fields = ['name', 'collate', 'character_set']

    def __init__(self, name, collate, character_set):
        self.name = name
        self.collate = collate
        self.character_set = character_set

    @classmethod
    def create(cls, context, instance_id, schemas):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
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
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
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
        for schema in schemas:
            guest_schema = guest_models.DatastoreSchema.deserialize(
                schema, verify=False)
            if guest_schema.name in cfg.get_ignored_dbs():
                continue

            model_schemas.append(Schema(guest_schema.name,
                                        guest_schema.collate,
                                        guest_schema.character_set))
        return model_schemas, next_marker

    @classmethod
    def find(cls, context, instance_id, schema_id):
        load_and_verify(context, instance_id,
                        enabled_datastore=['mysql', 'mariadb', 'postgresql'])
        client = create_guest_client(context, instance_id)
        model_schemas, _ = cls.load_with_client(client, 1, schema_id, True)
        if model_schemas and model_schemas[0].name == schema_id:
            return model_schemas[0]

        return None
