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
from oslo_utils import strutils

from trove.common import exception
from trove.common.i18n import _
from trove.common import models
from trove.common import pagination
from trove.common import timeutils
from trove.common import utils
from trove.db import db_query
from trove.db import get_db_api

LOG = logging.getLogger(__name__)


class DatabaseModelBase(models.ModelBase):
    _auto_generated_attrs = ['id']

    @classmethod
    def create(cls, **values):
        init_vals = {
            'id': utils.generate_uuid(),
            'created': timeutils.utcnow(),
        }
        if hasattr(cls, 'deleted'):
            init_vals['deleted'] = False
        init_vals.update(values)
        instance = cls(**init_vals)
        if not instance.is_valid():
            raise exception.InvalidModelError(errors=instance.errors)
        return instance.save()

    @property
    def db_api(self):
        return get_db_api()

    @property
    def preserve_on_delete(self):
        return hasattr(self, 'deleted') and hasattr(self, 'deleted_at')

    @classmethod
    def query(cls):
        return get_db_api()._base_query(cls)

    def save(self):
        if not self.is_valid():
            raise exception.InvalidModelError(errors=self.errors)
        self['updated'] = timeutils.utcnow()
        LOG.debug("Saving %(name)s: %(dict)s",
                  {'name': self.__class__.__name__,
                   'dict': strutils.mask_dict_password(self.__dict__)})
        return self.db_api.save(self)

    def delete(self):
        self['updated'] = timeutils.utcnow()
        LOG.debug("Deleting %(name)s: %(dict)s",
                  {'name': self.__class__.__name__,
                   'dict': strutils.mask_dict_password(self.__dict__)})

        if self.preserve_on_delete:
            self['deleted_at'] = timeutils.utcnow()
            self['deleted'] = True
            return self.db_api.save(self)
        else:
            return self.db_api.delete(self)

    def update(self, **values):
        for key in values:
            if hasattr(self, key):
                setattr(self, key, values[key])
        self['updated'] = timeutils.utcnow()
        return self.db_api.save(self)

    def __init__(self, **kwargs):
        self.merge_attributes(kwargs)
        if not self.is_valid():
            raise exception.InvalidModelError(errors=self.errors)

    def merge_attributes(self, values):
        """dict.update() behaviour."""
        for k, v in values.items():
            self[k] = v

    @classmethod
    def find_by(cls, context=None, **conditions):
        model = cls.get_by(**conditions)

        if model is None:
            raise exception.ModelNotFoundError(_("%(s_name)s Not Found") %
                                               {"s_name": cls.__name__})

        if ((context and not context.is_admin and hasattr(model, 'tenant_id')
             and model.tenant_id != context.project_id)):
            log_fmt = ("Tenant %(s_tenant)s tried to access "
                       "%(s_name)s, owned by %(s_owner)s.")
            exc_fmt = _("Tenant %(s_tenant)s tried to access "
                        "%(s_name)s, owned by %(s_owner)s.")
            msg_content = {
                "s_tenant": context.project_id,
                "s_name": cls.__name__,
                "s_owner": model.tenant_id}
            LOG.error(log_fmt, msg_content)
            raise exception.ModelNotFoundError(exc_fmt % msg_content)

        return model

    @classmethod
    def find_by_filter(cls, **kwargs):
        return db_query.find_by_filter(cls, **cls._process_conditions(kwargs))

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
