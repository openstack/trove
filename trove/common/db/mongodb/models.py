# Copyright 2016 Tesora, Inc.
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

from trove.common.db import models
from trove.common.i18n import _


class MongoDBSchema(models.DatastoreSchema):
    """Represents a MongoDB database and its associated properties."""

    @property
    def _max_schema_name_length(self):
        return 64

    def _is_valid_schema_name(self, value):
        # check against the invalid character set from
        # http://docs.mongodb.org/manual/reference/limits
        return not any(c in value for c in r'/\. "$')


class MongoDBUser(models.DatastoreUser):
    """Represents a MongoDB user and its associated properties.
    MongoDB users are identified using their name and database.
    Trove stores this as <database>.<username>
    """

    root_username = 'admin.root'

    def __init__(self, name=None, password=None, host=None, databases=None,
                 deserializing=False):
        super(MongoDBUser, self).__init__(name=name, password=password,
                                          host=host, databases=databases,
                                          deserializing=deserializing)
        if not deserializing:
            self._init_roles()

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value):
        self._update_name(username=value)

    @property
    def database(self):
        return MongoDBSchema.deserialize(self._database)

    @database.setter
    def database(self, value):
        self._update_name(database=value)

    def _validate_user_name(self, value):
        self._update_name(name=value)

    def _update_name(self, name=None, username=None, database=None):
        """Keep the name, username, and database values in sync."""
        if name:
            (database, username) = self._parse_name(name)
            if not (database and username):
                missing = 'username' if self.database else 'database'
                raise ValueError(_("MongoDB user's name missing %s.")
                                 % missing)
        else:
            if username:
                if not self.database:
                    raise ValueError(_('MongoDB user missing database.'))
                database = self.database.name
            else:  # database
                if not self.username:
                    raise ValueError(_('MongoDB user missing username.'))
                username = self.username
            name = '%s.%s' % (database, username)
        self._name = name
        self._username = username
        self._database = self._build_database_schema(database).serialize()

    @property
    def roles(self):
        return self._roles

    @roles.setter
    def roles(self, value):
        if isinstance(value, list):
            for role in value:
                self._add_role(role)
        else:
            self._add_role(value)

    def revoke_role(self, role):
        if role in self.roles:
            self._roles.remove(role)

    def _init_roles(self):
        if '_roles' not in self.__dict__:
            self._roles = []
            for db in self._databases:
                self._roles.append({'db': db['_name'], 'role': 'readWrite'})

    def _build_database_schema(self, name):
        return MongoDBSchema(name)

    def deserialize_schema(self, value):
        return MongoDBSchema.deserialize(value)

    @staticmethod
    def _parse_name(value):
        """The name will be <database>.<username>, so split it."""
        parts = value.split('.', 1)
        if len(parts) != 2:
            raise ValueError(_(
                'MongoDB user name "%s" not in <database>.<username> format.'
            ) % value)
        return parts[0], parts[1]

    @property
    def _max_user_name_length(self):
        return 128

    def _add_role(self, value):
        if not self._is_valid_role(value):
            raise ValueError(_('Role %s is invalid.') % value)
        self._roles.append(value)
        if value['role'] == 'readWrite':
            self.databases = value['db']

    def _is_valid_role(self, value):
        if not isinstance(value, dict):
            return False
        if not {'db', 'role'} == set(value):
            return False
        return True

    def verify_dict(self):
        super(MongoDBUser, self).verify_dict()
        self._init_roles()

    @property
    def schema_model(self):
        return MongoDBSchema

    def _create_checks(self):
        super(MongoDBUser, self)._create_checks()
        if not self.password:
            raise ValueError(_("MongoDB user to create is missing a "
                               "password."))
