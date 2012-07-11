# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging

from reddwarf.instance.models import DBInstance


LOG = logging.getLogger(__name__)


def load_accounts_summary(cls):
    # TODO(pdmars): This should probably be changed to a more generic
    # database filter query if one is added, however, this should suffice
    # for now.
    db_infos = DBInstance.find_all(deleted=False)
    tenant_ids_for_instances = [db_info.tenant_id for db_info in db_infos]
    tenant_ids = set(tenant_ids_for_instances)
    LOG.debug("All tenants with instances: %s" % tenant_ids)
    accounts = []
    for tenant_id in tenant_ids:
        num_instances = tenant_ids_for_instances.count(tenant_id)
        accounts.append({'id': tenant_id, 'num_instances': num_instances})
    return cls(accounts)


class AccountsSummary(object):

    def __init__(self, accounts):
        self.accounts = accounts

    @classmethod
    def load(cls):
        return load_accounts_summary(cls)
