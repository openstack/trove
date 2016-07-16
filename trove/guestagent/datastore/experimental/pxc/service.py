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

from trove.common import cfg
from trove.guestagent.datastore.galera_common import service as galera_service
from trove.guestagent.datastore.mysql_common import service as mysql_service

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class PXCApp(galera_service.GaleraApp):

    def __init__(self, status):
        super(PXCApp, self).__init__(
            status, mysql_service.BaseLocalSqlClient,
            mysql_service.BaseKeepAliveConnection)

    @property
    def mysql_service(self):
        result = super(PXCApp, self).mysql_service
        if result['type'] == 'sysvinit':
            result['cmd_bootstrap_galera_cluster'] = (
                "sudo service %s bootstrap-pxc" % result['service'])
        elif result['type'] == 'systemd':
            result['cmd_bootstrap_galera_cluster'] = (
                "sudo systemctl start %s@bootstrap.service"
                % result['service'])
        return result

    @property
    def cluster_configuration(self):
        return self.configuration_manager.get_value('mysqld')


class PXCRootAccess(mysql_service.BaseMySqlRootAccess):

    def __init__(self):
        super(PXCRootAccess, self).__init__(
            mysql_service.BaseLocalSqlClient,
            PXCApp(mysql_service.BaseMySqlAppStatus.get()))


class PXCAdmin(mysql_service.BaseMySqlAdmin):
    def __init__(self):
        super(PXCAdmin, self).__init__(
            mysql_service.BaseLocalSqlClient, PXCRootAccess(), PXCApp)
