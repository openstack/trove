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

import re

from trove.common.db import models


class PostgreSQLSchema(models.DatastoreSchema):
    """Represents a PostgreSQL schema and its associated properties."""

    name_regex = re.compile(str(r'^[\u0001-\u007F\u0080-\uFFFF]+[^\s]$'))

    def __init__(self, name=None, collate=None, character_set=None,
                 deserializing=False):
        super(PostgreSQLSchema, self).__init__(name=name,
                                               deserializing=deserializing)
        self.collate = collate
        self.character_set = character_set

    @property
    def collate(self):
        return self._collate

    @collate.setter
    def collate(self, value):
        self._collate = value

    @property
    def character_set(self):
        return self._character_set

    @character_set.setter
    def character_set(self, value):
        self._character_set = value

    @property
    def _max_schema_name_length(self):
        return 63

    def _is_valid_schema_name(self, value):
        return self.name_regex.match(value) is not None


class PostgreSQLUser(models.DatastoreUser):
    """Represents a PostgreSQL user and its associated properties."""

    root_username = 'postgres'

    @property
    def _max_user_name_length(self):
        return 63

    @property
    def schema_model(self):
        return PostgreSQLSchema
