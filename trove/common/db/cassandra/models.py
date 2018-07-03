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


class CassandraSchema(models.DatastoreSchema):
    """Represents a Cassandra schema and its associated properties.

    Keyspace names are 32 or fewer alpha-numeric characters and underscores,
    the first of which is an alpha character.
    """

    @property
    def _max_schema_name_length(self):
        return 32

    def _is_valid_schema_name(self, value):
        return not any(c in value for c in r'/\. "$')


class CassandraUser(models.DatastoreUser):
    """Represents a Cassandra user and its associated properties."""

    root_username = 'cassandra'

    @property
    def _max_user_name_length(self):
        return 65535

    @property
    def schema_model(self):
        return CassandraSchema
