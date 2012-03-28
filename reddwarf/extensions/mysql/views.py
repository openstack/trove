# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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


class UserView(object):

    def __init__(self, user):
        self.user = user

    def data(self):
        user_dict = {
            "name": self.user.name,
            "databases": self.user.databases
        }
        return {"users": user_dict}


class UsersView(object):

    def __init__(self, users):
        self.users = users

    def data(self):
        data = []
        # These are model instances
        for user in self.users:
            data.append(UserView(user).data())

        return data


class RootCreatedView(UserView):

    def data(self):
        user_dict = {
            "name": self.user.name,
            "password": self.user.password
        }
        return {"user": user_dict}


class RootEnabledView(object):

    def __init__(self, is_root_enabled):
        self.is_root_enabled = is_root_enabled

    def data(self):
        return {'rootEnabled': self.is_root_enabled}


class SchemaView(object):

    def __init__(self, schema):
        self.schema = schema

    def data(self):
        schema_dict = {
            "name": self.schema.name,
            "collate": self.schema.collate,
            "character_set": self.schema.character_set
        }
        return {"databases": schema_dict}


class SchemasView(object):

    def __init__(self, schemas):
        self.schemas = schemas

    def data(self):
        data = []
        # These are model instances
        for schema in self.schemas:
            data.append(SchemaView(schema).data())

        return data
