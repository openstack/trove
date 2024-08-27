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

from pathlib import Path


from alembic import command as alembic_command
from alembic import config as alembic_config
from alembic import migration as alembic_migration
from alembic.script import ScriptDirectory
from oslo_log import log as logging
import sqlalchemy as sa
import sqlalchemy.exc
from sqlalchemy import text

from trove.common import exception
from trove.db.sqlalchemy import session

LOG = logging.getLogger(__name__)

ALEMBIC_INIT_VERSION = '906cffda7b29'
ALEMBIC_LATEST_VERSION = '5c68b4fb3cd1'


def list(query_func, *args, **kwargs):
    query = query_func(*args, **kwargs)
    res = query.all()
    query.session.commit()
    return res


def count(query, *args, **kwargs):
    query = query(*args, **kwargs)
    res = query.count()
    query.session.commit()
    return res


def first(query, *args, **kwargs):
    query = query(*args, **kwargs)
    res = query.first()
    query.session.commit()
    return res


def join(query, model, *args):
    query = query(model)
    res = query.join(*args)
    query.session.commit()
    return res


def find_all(model, **conditions):
    return _query_by(model, **conditions)


def find_all_by_limit(query_func, model, conditions, limit, marker=None,
                      marker_column=None):
    query = _limits(query_func, model, conditions, limit, marker,
                    marker_column)
    res = query.all()
    query.session.commit()
    return res


def find_by(model, **kwargs):
    query = _query_by(model, **kwargs)
    res = query.first()
    query.session.commit()
    return res


def find_by_filter(model, **kwargs):
    filters = kwargs.pop('filters', [])
    return _query_by_filter(model, *filters, **kwargs)


def save(model):
    try:
        db_session = session.get_session()
        with db_session.begin():
            model = db_session.merge(model)
            db_session.flush()
            return model
    except sqlalchemy.exc.IntegrityError as error:
        raise exception.DBConstraintError(model_name=model.__class__.__name__,
                                          error=str(error.orig))


def delete(model):
    db_session = session.get_session()
    with db_session.begin():
        model = db_session.merge(model)
        db_session.delete(model)
        db_session.flush()


def delete_all(query_func, model, **conditions):
    query = query_func(model, **conditions)
    query.delete()
    query.session.commit()


def update(model, **values):
    for k, v in values.items():
        model[k] = v


def update_all(query_func, model, conditions, values):
    query = query_func(model, **conditions)
    query.update()
    query.session.commit()


def configure_db(*plugins):
    session.configure_db()
    configure_db_for_plugins(*plugins)


def configure_db_for_plugins(*plugins):
    for plugin in plugins:
        session.configure_db(models_mapper=plugin.mapper)


def drop_db():
    session.drop_db()


def clean_db():
    session.clean_db()


def _get_alembic_revision(config):
    script = ScriptDirectory.from_config(config)
    current_revision = script.get_current_head()
    if current_revision is not None:
        return current_revision
    return "head"


def _migrate_legacy_database(config):
    """Check if database is a legacy sqlalchemy-migrate-managed database.

    If it is, migrate it by "stamping" the initial alembic schema.
    """
    # If the database doesn't have the sqlalchemy-migrate legacy migration
    # table, we don't have anything to do
    engine = session.get_engine()
    if not sa.inspect(engine).has_table('migrate_version'):
        return

    # Likewise, if we've already migrated to alembic, we don't have anything to
    # do
    with engine.begin() as connection:
        context = alembic_migration.MigrationContext.configure(connection)
        if context.get_current_revision():
            return

    # We have legacy migrations but no alembic migration. Stamp (dummy apply)
    # the initial alembic migration.

    LOG.info(
        'The database is still under sqlalchemy-migrate control; '
        'fake applying the initial alembic migration'
    )
    # In case we upgrade from the branch prior to stable/2023.2
    if sa.inspect(engine).has_table('migrate_version'):
        # for the deployment prior to Bobocat
        query = text("SELECT version FROM migrate_version")
        with engine.connect() as connection:
            result = connection.execute(query)
        cur_version = result.first().values()[0]
        LOG.info("current version is %s", cur_version)
        if cur_version == 48:
            alembic_command.stamp(config, ALEMBIC_INIT_VERSION)
        elif cur_version > 48:
            # we already upgrade to the latest branch, use the latest
            # version(5c68b4fb3cd1)
            alembic_command.stamp(config, ALEMBIC_LATEST_VERSION)
        else:
            message = ("You need to upgrade trove database to a version "
                       "between Wallaby and Bobocat, and then upgrade to "
                       "the latest.")
            raise exception.BadRequest(message)


def _configure_alembic(conf=None):
    if conf is None:
        conf = conf.CONF
    alembic_ini = Path(__file__).joinpath('..', 'alembic.ini').resolve()
    if alembic_ini.exists():
        # alembic configuration
        config = alembic_config.Config(alembic_ini)
        # override the database configuration from the file
        config.set_main_option('sqlalchemy.url',
                               conf['database']['connection'])
        # override the logger configuration from the file
        # https://stackoverflow.com/a/42691781/613428
        config.attributes['configure_logger'] = False
        return config
    else:
        # return None if no alembic.ini exists
        return None


def db_sync(conf=None, version=None, repo_path=None):
    config = _configure_alembic(conf=conf)
    if config:
        # Check the version
        if version is None:
            version = _get_alembic_revision(config)
        # Raise an exception in sqlalchemy-migrate style
        if version is not None and version.isdigit():
            raise exception.InvalidValue(
                'You requested an sqlalchemy-migrate database version;'
                'this is no longer supported'
            )
        # Upgrade to a later version using alembic
        _migrate_legacy_database(config)
        alembic_command.upgrade(config, version)
    else:
        raise exception.BadRequest('sqlalchemy-migrate is '
                                   'no longer supported')


def db_upgrade(conf=None, version=None, repo_path=None):
    config = _configure_alembic(conf=conf)
    if config:
        # Check the version
        if version is None:
            version = 'head'
        # Raise an exception in sqlalchemy-migrate style
        if version.isdigit():
            raise exception.InvalidValue(
                'You requested an sqlalchemy-migrate database version;'
                'this is no longer supported'
            )
        # Upgrade to a later version using alembic
        _migrate_legacy_database(config)
        alembic_command.upgrade(config, version)
    else:
        raise exception.BadRequest('sqlalchemy-migrate is '
                                   'no longer supported')


def db_reset(*plugins):
    drop_db()
    db_sync()
    configure_db()


def _base_query(cls):
    db_session = session.get_session()
    query = db_session.query(cls)
    return query


def _query_by(cls, **conditions):
    query = _base_query(cls)
    if conditions:
        query = query.filter_by(**conditions)
    return query


def _query_by_filter(cls, *filters, **conditions):
    query = _query_by(cls, **conditions)
    if filters:
        query = query.filter(*filters)
    return query


def _limits(query_func, model, conditions, limit, marker, marker_column=None):
    query = query_func(model, **conditions)
    marker_column = marker_column or model.id
    if marker:
        query = query.filter(marker_column > marker)
    return query.order_by(marker_column).limit(limit)
