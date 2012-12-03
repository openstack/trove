#    Copyright 2011 OpenStack LLC
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

from reddwarf.db import get_db_api
from reddwarf.db import db_query
from reddwarf.common import exception
from reddwarf.common import models
from reddwarf.common import pagination
from reddwarf.common import utils
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


class DatabaseModelBase(models.ModelBase):
    _auto_generated_attrs = ['id']

    @classmethod
    def create(cls, **values):
        values['id'] = utils.generate_uuid()
        values['created'] = utils.utcnow()
        instance = cls(**values).save()
        if not instance.is_valid():
            raise exception.InvalidModelError(errors=instance.errors)
        return instance

    @property
    def db_api(self):
        return get_db_api()

    def save(self):
        if not self.is_valid():
            raise exception.InvalidModelError(errors=self.errors)
        self['updated'] = utils.utcnow()
        LOG.debug(_("Saving %s: %s") %
                  (self.__class__.__name__, self.__dict__))
        return self.db_api.save(self)

    def delete(self):
        self['updated'] = utils.utcnow()
        LOG.debug(_("Deleting %s: %s") %
                  (self.__class__.__name__, self.__dict__))
        return self.db_api.delete(self)

    def __init__(self, **kwargs):
        self.merge_attributes(kwargs)
        if not self.is_valid():
            raise exception.InvalidModelError(errors=self.errors)

    def merge_attributes(self, values):
        """dict.update() behaviour."""
        for k, v in values.iteritems():
            self[k] = v

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
    def find_all(cls, **kwargs):
        return db_query.find_all(cls, **cls._process_conditions(kwargs))

    @classmethod
    def _process_conditions(cls, raw_conditions):
        """Override in inheritors to format/modify any conditions."""
        return raw_conditions

    @classmethod
    def find_by_pagination(cls, collection_type, collection_query,
                           paginated_url, **kwargs):
        elements, next_marker = collection_query.paginated_collection(**kwargs)

        return pagination.PaginatedDataView(collection_type,
                                            elements,
                                            paginated_url,
                                            next_marker)
