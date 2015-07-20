#    Copyright 2011 OpenStack Foundation
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


from oslo_log import log as logging

from trove.common import cfg
from trove.common import utils
from trove.db import models as dbmodels

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def enum(**enums):
    return type('Enum', (), enums)


class Quota(dbmodels.DatabaseModelBase):
    """Defines the base model class for a quota."""

    _data_fields = ['created', 'updated', 'tenant_id', 'resource',
                    'hard_limit', 'id']

    def __init__(self, tenant_id, resource, hard_limit,
                 id=utils.generate_uuid(), created=utils.utcnow(),
                 update=utils.utcnow()):
        self.tenant_id = tenant_id
        self.resource = resource
        self.hard_limit = hard_limit
        self.id = id
        self.created = created
        self.update = update


class QuotaUsage(dbmodels.DatabaseModelBase):
    """Defines the quota usage for a tenant."""

    _data_fields = ['created', 'updated', 'tenant_id', 'resource',
                    'in_use', 'reserved', 'id']


class Reservation(dbmodels.DatabaseModelBase):
    """Defines the reservation for a quota."""

    _data_fields = ['created', 'updated', 'usage_id',
                    'id', 'delta', 'status']

    Statuses = enum(NEW='New',
                    RESERVED='Reserved',
                    COMMITTED='Committed',
                    ROLLEDBACK='Rolled Back')


def persisted_models():
    return {
        'quotas': Quota,
        'quota_usages': QuotaUsage,
        'reservations': Reservation,
    }


class Resource(object):
    """Describe a single resource for quota checking."""

    INSTANCES = 'instances'
    VOLUMES = 'volumes'
    BACKUPS = 'backups'

    def __init__(self, name, flag=None):
        """
        Initializes a Resource.

        :param name: The name of the resource, i.e., "volumes".
        :param flag: The name of the flag or configuration option
                     which specifies the default value of the quota
                     for this resource.
        """

        self.name = name
        self.flag = flag

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return (isinstance(other, Resource) and
                self.name == other.name and
                self.flag == other.flag)

    @property
    def default(self):
        """Return the default value of the quota."""

        return CONF[self.flag] if self.flag is not None else -1
