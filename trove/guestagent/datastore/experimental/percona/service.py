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

from oslo_log import log as logging
from trove.guestagent.datastore.mysql import service_base

LOG = logging.getLogger(__name__)


class KeepAliveConnection(service_base.BaseKeepAliveConnection):
    pass


class MySqlAppStatus(service_base.BaseMySqlAppStatus):
    pass


class LocalSqlClient(service_base.BaseLocalSqlClient):
    pass


class MySqlApp(service_base.BaseMySqlApp):
    def __init__(self, status):
        super(MySqlApp, self).__init__(status, LocalSqlClient,
                                       KeepAliveConnection)


class MySqlRootAccess(service_base.BaseMySqlRootAccess):
    def __init__(self):
        super(MySqlRootAccess, self).__init__(LocalSqlClient,
                                              MySqlApp(MySqlAppStatus.get()))


class MySqlAdmin(service_base.BaseMySqlAdmin):
    def __init__(self):
        super(MySqlAdmin, self).__init__(LocalSqlClient, MySqlRootAccess(),
                                         MySqlApp)
