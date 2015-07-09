# Copyright 2015 Tesora, Inc.
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
#

from oslo_utils import importutils
from trove.common import cfg
from trove.guestagent.datastore.mysql import manager_base
from trove.guestagent.strategies.replication import get_replication_strategy

CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'mysql'
REPLICATION_STRATEGY = CONF.get(MANAGER).replication_strategy
REPLICATION_NAMESPACE = CONF.get(MANAGER).replication_namespace
REPLICATION_STRATEGY_CLASS = get_replication_strategy(REPLICATION_STRATEGY,
                                                      REPLICATION_NAMESPACE)

MYSQL_APP = "trove.guestagent.datastore.experimental.mariadb." \
            "service.MySqlApp"
MYSQL_APP_STATUS = "trove.guestagent.datastore.experimental.mariadb." \
                   "service.MySqlAppStatus"
MYSQL_ADMIN = "trove.guestagent.datastore.experimental.mariadb.service." \
              "MySqlAdmin"


class Manager(manager_base.BaseMySqlManager):

    def __init__(self):
        mysql_app = importutils.import_class(MYSQL_APP)
        mysql_app_status = importutils.import_class(MYSQL_APP_STATUS)
        mysql_admin = importutils.import_class(MYSQL_ADMIN)

        super(Manager, self).__init__(mysql_app, mysql_app_status,
                                      mysql_admin, REPLICATION_STRATEGY,
                                      REPLICATION_NAMESPACE,
                                      REPLICATION_STRATEGY_CLASS, MANAGER)
