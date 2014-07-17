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

from datetime import datetime
from datetime import timedelta

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.db import get_db_api
from trove.db import models as dbmodels
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

AGENT_HEARTBEAT = CONF.agent_heartbeat_time


def persisted_models():
    return {'agent_heartbeats': AgentHeartBeat}


class AgentHeartBeat(dbmodels.DatabaseModelBase):
    """Defines the state of a Guest Agent."""

    _data_fields = ['instance_id', 'updated_at', 'guest_agent_version',
                    'deleted', 'deleted_at']
    _table_name = 'agent_heartbeats'

    def __init__(self, **kwargs):
        super(AgentHeartBeat, self).__init__(**kwargs)

    @classmethod
    def create(cls, **values):
        values['id'] = utils.generate_uuid()
        heartbeat = cls(**values).save()
        if not heartbeat.is_valid():
            raise exception.InvalidModelError(errors=heartbeat.errors)
        return heartbeat

    def save(self):
        if not self.is_valid():
            raise exception.InvalidModelError(errors=self.errors)
        self['updated_at'] = utils.utcnow()
        LOG.debug("Saving %(name)s: %(dict)s" %
                  {'name': self.__class__.__name__, 'dict': self.__dict__})
        return get_db_api().save(self)

    @classmethod
    def find_all_by_version(cls, guest_agent_version, deleted=0):
        if guest_agent_version is None:
            raise exception.ModelNotFoundError()

        heartbeats = cls.find_all(guest_agent_version=guest_agent_version,
                                  deleted=deleted)

        if heartbeats is None or heartbeats.count() == 0:
            raise exception.ModelNotFoundError(
                guest_agent_version=guest_agent_version)

        return heartbeats

    @classmethod
    def find_by_instance_id(cls, instance_id):
        if instance_id is None:
            raise exception.ModelNotFoundError(instance_id=instance_id)

        try:
            return cls.find_by(instance_id=instance_id)

        except exception.NotFound:
            LOG.exception(_("Error finding instance %s") % instance_id)
            raise exception.ModelNotFoundError(instance_id=instance_id)

    @staticmethod
    def is_active(agent):
        return (datetime.now() - agent.updated_at <
                timedelta(seconds=AGENT_HEARTBEAT))
