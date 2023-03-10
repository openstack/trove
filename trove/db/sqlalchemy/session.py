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

from oslo_db.sqlalchemy import enginefacade
from oslo_log import log as logging
from sqlalchemy import MetaData

from trove.common import cfg
from trove.common.i18n import _
from trove.db.sqlalchemy import mappers

_FACADE = None

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def configure_db(models_mapper=None):
    facade = _create_facade()
    if models_mapper:
        models_mapper.map(facade)
    else:
        from trove.backup import models as backup_models
        from trove.cluster import models as cluster_models
        from trove.conductor import models as conductor_models
        from trove.configuration import models as configurations_models
        from trove.datastore import models as datastores_models
        from trove.dns import models as dns_models
        from trove.extensions.common import models as common_models
        from trove.extensions.security_group import models as secgrp_models
        from trove.guestagent import models as agent_models
        from trove.instance import models as base_models
        from trove.module import models as module_models
        from trove.quota import models as quota_models

        model_modules = [
            base_models,
            datastores_models,
            dns_models,
            common_models,
            agent_models,
            quota_models,
            backup_models,
            secgrp_models,
            configurations_models,
            conductor_models,
            cluster_models,
            module_models
        ]

        models = {}
        for module in model_modules:
            models.update(module.persisted_models())
        mappers.map(get_engine(), models)


def _create_facade():
    global _FACADE
    if _FACADE is None:
        ctx = enginefacade.transaction_context()
        _FACADE = ctx.writer
    return _FACADE


def _check_facade():
    if _FACADE is None:
        LOG.exception("***The Database has not been setup!!!***")
        raise RuntimeError(
            _("***The Database has not been setup!!!***"))


def get_facade():
    _check_facade()
    return _FACADE


def get_engine():
    _create_facade()
    return _FACADE.get_engine()


def get_session(**kwargs):
    facade = _create_facade()
    sessionmaker = facade.get_sessionmaker()
    return sessionmaker(**kwargs)


def raw_query(model, **kwargs):
    return get_session(**kwargs).query(model)


def clean_db():
    engine = get_engine()
    meta = MetaData()
    meta.bind = engine
    meta.reflect(bind=engine)
    with contextlib.closing(engine.connect()) as con:
        trans = con.begin()
        for table in reversed(meta.sorted_tables):
            if table.name != "migrate_version":
                con.execute(table.delete())
        trans.commit()


def drop_db():
    _create_facade()
    engine = get_engine()
    meta = MetaData()
    meta.bind = engine
    meta.reflect()
    meta.drop_all()
