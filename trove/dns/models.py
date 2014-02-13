# Copyright 2010-2011 OpenStack Foundation
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

"""
Model classes that map instance Ip to dns record.
"""


from trove.db import get_db_api
from trove.common import exception
from trove.common.models import ModelBase
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


def persisted_models():
    return {
        'dns_records': DnsRecord,
    }


class DnsRecord(ModelBase):

    _data_fields = ['name', 'record_id']
    _table_name = 'dns_records'

    def __init__(self, name, record_id):
        self.name = name
        self.record_id = record_id

    @classmethod
    def create(cls, **values):
        record = cls(**values).save()
        if not record.is_valid():
            raise exception.InvalidModelError(errors=record.errors)
        return record

    def save(self):
        if not self.is_valid():
            raise exception.InvalidModelError(errors=self.errors)
        LOG.debug(_("Saving %(name)s: %(dict)s") %
                  {'name': self.__class__.__name__, 'dict': self.__dict__})
        return get_db_api().save(self)

    def delete(self):
        LOG.debug(_("Deleting %(name)s: %(dict)s") %
                  {'name': self.__class__.__name__, 'dict': self.__dict__})
        return get_db_api().delete(self)

    @classmethod
    def find_by(cls, **conditions):
        model = cls.get_by(**conditions)
        if model is None:
            raise exception.ModelNotFoundError(_("%s Not Found") %
                                               cls.__name__)
        return model

    @classmethod
    def get_by(cls, **kwargs):
        return get_db_api().find_by(cls, **cls._process_conditions(kwargs))

    @classmethod
    def _process_conditions(cls, raw_conditions):
        """Override in inheritors to format/modify any conditions."""
        return raw_conditions
