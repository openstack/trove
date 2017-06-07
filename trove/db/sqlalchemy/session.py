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
import threading

from oslo_db.sqlalchemy import session
from oslo_log import log as logging
from sqlalchemy import MetaData

from trove.common import cfg
from trove.common.i18n import _
from trove.db.sqlalchemy import mappers

_FACADE = None
_LOCK = threading.Lock()


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def configure_db(options, models_mapper=None):
    facade = _create_facade(options)
    if models_mapper:
        models_mapper.map(facade)
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
        from trove.module import models as module_models
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
            module_models
        ]

        models = {}
        for module in model_modules:
            models.update(module.persisted_models())
        mappers.map(get_engine(), models)


def _create_facade(options):
    global _LOCK, _FACADE
    # TODO(mvandijk): Refactor this once oslo.db spec is implemented:
    # https://specs.openstack.org/openstack/oslo-specs/specs/kilo/
    #     make-enginefacade-a-facade.html
    if _FACADE is None:
        with _LOCK:
            if _FACADE is None:
                conf = CONF.database
                # pop the deprecated config option 'query_log'
                if conf.query_log:
                    if conf.connection_debug < 50:
                        conf['connection_debug'] = 50
                    LOG.warning(_('Configuration option "query_log" has been '
                                  'depracated. Use "connection_debug" '
                                  'instead. Setting connection_debug = '
                                  '%(debug_level)s instead.'),
                                conf.get('connection_debug'))
                # TODO(mvandijk): once query_log is removed,
                #                 use enginefacade.from_config() instead
                database_opts = dict(CONF.database)
                database_opts.pop('query_log')
                _FACADE = session.EngineFacade(
                    options['database']['connection'],
                    **database_opts
                )
    return _FACADE


def _check_facade():
    if _FACADE is None:
        msg = _("***The Database has not been setup!!!***")
        LOG.exception(msg)
        raise RuntimeError(msg)


def get_facade():
    _check_facade()
    return _FACADE


def get_engine(use_slave=False):
    _check_facade()
    return _FACADE.get_engine(use_slave=use_slave)


def get_session(**kwargs):
    return get_facade().get_session(**kwargs)


def raw_query(model, **kwargs):
    return get_session(**kwargs).query(model)


def clean_db():
    engine = get_engine()
    meta = MetaData()
    meta.bind = engine
    meta.reflect()
    with contextlib.closing(engine.connect()) as con:
        trans = con.begin()
        for table in reversed(meta.sorted_tables):
            if table.name != "migrate_version":
                con.execute(table.delete())
        trans.commit()


def drop_db(options):
    if options:
        _create_facade(options)
    engine = get_engine()
    meta = MetaData()
    meta.bind = engine
    meta.reflect()
    meta.drop_all()
