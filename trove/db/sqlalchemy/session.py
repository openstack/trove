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

import contextlib

import osprofiler.sqlalchemy
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy import MetaData
from sqlalchemy.orm import sessionmaker

from trove.common import cfg
from trove.common.i18n import _
from trove.db.sqlalchemy import mappers
from trove.openstack.common import log as logging

_ENGINE = None
_MAKER = None


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def configure_db(options, models_mapper=None):
    global _ENGINE
    if not _ENGINE:
        _ENGINE = _create_engine(options)
    if models_mapper:
        models_mapper.map(_ENGINE)
    else:
        from trove.backup import models as backup_models
        from trove.cluster import models as cluster_models
        from trove.conductor import models as conductor_models
        from trove.configuration import models as configurations_models
        from trove.datastore import models as datastores_models
        from trove.dns import models as dns_models
        from trove.extensions.mysql import models as mysql_models
        from trove.extensions.security_group import models as secgrp_models
        from trove.guestagent import models as agent_models
        from trove.instance import models as base_models
        from trove.quota import models as quota_models

        model_modules = [
            base_models,
            datastores_models,
            dns_models,
            mysql_models,
            agent_models,
            quota_models,
            backup_models,
            secgrp_models,
            configurations_models,
            conductor_models,
            cluster_models,
        ]

        models = {}
        for module in model_modules:
            models.update(module.persisted_models())
        mappers.map(_ENGINE, models)


def _create_engine(options):
    engine_args = {
        "pool_recycle": CONF.database.idle_timeout,
        "echo": CONF.database.query_log
    }
    LOG.info(_("Creating SQLAlchemy engine with args: %s") % engine_args)
    db_engine = create_engine(options['database']['connection'], **engine_args)
    if CONF.profiler.enabled and CONF.profiler.trace_sqlalchemy:
        osprofiler.sqlalchemy.add_tracing(sqlalchemy, db_engine, "db")
    return db_engine


def get_session(autocommit=True, expire_on_commit=False):
    """Helper method to grab session."""
    global _MAKER, _ENGINE
    if not _MAKER:
        if not _ENGINE:
            msg = "***The Database has not been setup!!!***"
            LOG.exception(msg)
            raise RuntimeError(msg)
        _MAKER = sessionmaker(bind=_ENGINE,
                              autocommit=autocommit,
                              expire_on_commit=expire_on_commit)
    return _MAKER()


def raw_query(model, autocommit=True, expire_on_commit=False):
    return get_session(autocommit, expire_on_commit).query(model)


def clean_db():
    global _ENGINE
    meta = MetaData()
    meta.reflect(bind=_ENGINE)
    with contextlib.closing(_ENGINE.connect()) as con:
        trans = con.begin()
        for table in reversed(meta.sorted_tables):
            if table.name != "migrate_version":
                con.execute(table.delete())
        trans.commit()


def drop_db(options):
    meta = MetaData()
    engine = _create_engine(options)
    meta.bind = engine
    meta.reflect()
    meta.drop_all()
