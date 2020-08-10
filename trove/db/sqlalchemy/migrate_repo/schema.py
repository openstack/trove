# Copyright 2011 OpenStack Foundation
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

"""Various conveniences used for migration scripts."""

from oslo_log import log as logging
import sqlalchemy.types


logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')


class String(sqlalchemy.types.String):
    def __init__(self, length, *args, **kwargs):
        super(String, self).__init__(*args, length=length, **kwargs)


class Text(sqlalchemy.types.Text):
    def __init__(self, length=None, *args, **kwargs):
        super(Text, self).__init__(*args, **kwargs)
        self.with_variant(sqlalchemy.types.Text(length=length), 'mysql')


class Boolean(sqlalchemy.types.Boolean):
    def __init__(self, create_constraint=True, name=None, *args, **kwargs):
        super(Boolean, self).__init__(*args,
                                      create_constraint=create_constraint,
                                      name=name,
                                      **kwargs)


class DateTime(sqlalchemy.types.DateTime):
    def __init__(self, timezone=False, *args, **kwargs):
        super(DateTime, self).__init__(*args,
                                       timezone=timezone,
                                       **kwargs)


class Integer(sqlalchemy.types.Integer):
    def __init__(self, *args, **kwargs):
        super(Integer, self).__init__(*args, **kwargs)


class BigInteger(sqlalchemy.types.BigInteger):
    def __init__(self, *args, **kwargs):
        super(BigInteger, self).__init__(*args, **kwargs)


class Float(sqlalchemy.types.Float):
    def __init__(self, *args, **kwargs):
        super(Float, self).__init__(*args, **kwargs)


class Json(sqlalchemy.types.JSON):
    def __init__(self, *args, **kwargs):
        super(Json, self).__init__(*args, **kwargs)


def create_tables(tables):
    for table in tables:
        logger.info("creating table %(table)s", {'table': table})
        table.create()


def drop_tables(tables):
    for table in tables:
        logger.info("dropping table %(table)s", {'table': table})
        table.drop()


def Table(name, metadata, *args, **kwargs):
    return sqlalchemy.schema.Table(name, metadata, *args,
                                   mysql_engine='INNODB', **kwargs)
