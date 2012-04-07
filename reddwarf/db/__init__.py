# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

import optparse

from reddwarf.common import utils
from reddwarf.common import config


db_api = utils.import_object(config.Config.get("db_api_implementation",
    "reddwarf.db.sqlalchemy.api"))


class Query(object):
    """Mimics sqlalchemy query object.

    This class allows us to store query conditions and use them with
    bulk updates and deletes just like sqlalchemy query object.
    Using this class makes the models independent of sqlalchemy

    """
    def __init__(self, model, query_func, **conditions):
        self._query_func = query_func
        self._model = model
        self._conditions = conditions

    def all(self):
        return db_api.list(self._query_func, self._model, **self._conditions)

    def count(self):
        return db_api.count(self._query_func, self._model, **self._conditions)

    def __iter__(self):
        return iter(self.all())

    def update(self, **values):
        db_api.update_all(self._query_func, self._model, self._conditions,
            values)

    def delete(self):
        db_api.delete_all(self._query_func, self._model, **self._conditions)

    def limit(self, limit=200, marker=None, marker_column=None):
        return db_api.find_all_by_limit(self._query_func,
            self._model,
            self._conditions,
            limit=limit,
            marker=marker,
            marker_column=marker_column)

    def paginated_collection(self, limit=200, marker=None,
                             marker_column=None):
        collection = self.limit(int(limit) + 1, marker, marker_column)
        if len(collection) > int(limit):
            return (collection[0:-1], collection[-2]['id'])
        return (collection, None)


class Queryable(object):

    def __getattr__(self, item):
        return lambda model, **conditions: Query(
            model, query_func=getattr(db_api, item), **conditions)

db_query = Queryable()


def add_options(parser):
    """Adds any configuration options that the db layer might have.

    :param parser: An optparse.OptionParser object
    :retval None

    """
    help_text = ("The following configuration options are specific to the "
                 "Reddwarf database.")

    group = optparse.OptionGroup(parser,
        "Registry Database Options",
        help_text)
    group.add_option('--sql-connection',
        metavar="CONNECTION",
        default=None,
        help="A valid SQLAlchemy connection string for the "
             "registry database. Default: %default")
    parser.add_option_group(group)
