# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import sqlalchemy.exc
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.orm import aliased

from trove.common import exception
from trove.common import utils
from trove.db.sqlalchemy import migration
from trove.db.sqlalchemy import mappers
from trove.db.sqlalchemy import session


def list(query_func, *args, **kwargs):
    return query_func(*args, **kwargs).all()


def count(query, *args, **kwargs):
    return query(*args, **kwargs).count()


def find_all(model, **conditions):
    return _query_by(model, **conditions)


def find_all_by_limit(query_func, model, conditions, limit, marker=None,
                      marker_column=None):
    return _limits(query_func, model, conditions, limit, marker,
                   marker_column).all()


def find_by(model, **kwargs):
    return _query_by(model, **kwargs).first()


def save(model):
    try:
        db_session = session.get_session()
        model = db_session.merge(model)
        db_session.flush()
        return model
    except sqlalchemy.exc.IntegrityError as error:
        raise exception.DBConstraintError(model_name=model.__class__.__name__,
                                          error=str(error.orig))


def delete(model):
    db_session = session.get_session()
    model = db_session.merge(model)
    db_session.delete(model)
    db_session.flush()


def delete_all(query_func, model, **conditions):
    query_func(model, **conditions).delete()


def update(model, **values):
    for k, v in values.iteritems():
        model[k] = v


def update_all(query_func, model, conditions, values):
    query_func(model, **conditions).update(values)


def configure_db(options, *plugins):
    session.configure_db(options)
    configure_db_for_plugins(options, *plugins)


def configure_db_for_plugins(options, *plugins):
    for plugin in plugins:
        session.configure_db(options, models_mapper=plugin.mapper)


def drop_db(options):
    session.drop_db(options)


def clean_db():
    session.clean_db()


def db_sync(options, version=None, repo_path=None):
    migration.db_sync(options, version, repo_path)


def db_upgrade(options, version=None, repo_path=None):
    migration.upgrade(options, version, repo_path)


def db_downgrade(options, version, repo_path=None):
    migration.downgrade(options, version, repo_path)


def db_reset(options, *plugins):
    drop_db(options)
    db_sync(options)
    configure_db(options)


def _base_query(cls):
    return session.get_session().query(cls)


def _query_by(cls, **conditions):
    query = _base_query(cls)
    if conditions:
        query = query.filter_by(**conditions)
    return query


def _limits(query_func, model, conditions, limit, marker, marker_column=None):
    query = query_func(model, **conditions)
    marker_column = marker_column or model.id
    if marker:
        query = query.filter(marker_column > marker)
    return query.order_by(marker_column).limit(limit)
