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

"""Model classes that form the core of instances functionality."""

import logging
import netaddr

from reddwarf import db

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import utils
from novaclient.v1_1.client import Client

LOG = logging.getLogger('reddwarf.database.models')

PROXY_ADMIN_USER = config.Config.get('reddwarf_proxy_admin_user', 'admin')
PROXY_ADMIN_PASS = config.Config.get('reddwarf_proxy_admin_pass', '3de4922d8b6ac5a1aad9')
PROXY_ADMIN_TENANT_NAME = config.Config.get('reddwarf_proxy_admin_tenant_name', 'admin')
PROXY_AUTH_URL = config.Config.get('reddwarf_auth_url', 'http://0.0.0.0:5000/v2.0')

class ModelBase(object):

    _data_fields = []
    _auto_generated_attrs = []

    def _validate(self):
        pass

    def data(self, **options):
        data_fields = self._data_fields + self._auto_generated_attrs
        return dict([(field, self[field]) for field in data_fields])

    def is_valid(self):
        self.errors = {}
#        self._validate_columns_type()
#        self._before_validate()
#        self._validate()
        return self.errors == {}

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def __eq__(self, other):
        if not hasattr(other, 'id'):
            return False
        return type(other) == type(self) and other.id == self.id

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return self.id.__hash__()


class RemoteModelBase(ModelBase):

    # This should be set by the remote model during init time
    # The data() method will be using this
    _data_object = None

    @classmethod
    def get_client(cls, proxy_token):
        client = Client(PROXY_ADMIN_USER, PROXY_ADMIN_PASS,
            PROXY_ADMIN_TENANT_NAME, PROXY_AUTH_URL, token=proxy_token)
        client.authenticate()
        return client

    def data_item(self, data_object):
        data_fields = self._data_fields + self._auto_generated_attrs
        return dict([(field, getattr(data_object,field)) for field in data_fields])

    # data magic that will allow for a list of _data_object or a single item
    # if the object is a list, it will turn it into a list of hash's again
    def data(self, **options):
        if self._data_object is None:
            raise LookupError("data object is None")
        if isinstance(self._data_object, list):
            return [self.data_item(item) for item in self._data_object]
        else:
            return self.data_item(self._data_object)


class Instance(RemoteModelBase):

    _data_fields = ['name', 'status', 'updated', 'id', 'flavor']

    def __init__(self, proxy_token, uuid):
        self._data_object = self.get_client(proxy_token).servers.get(uuid)


class Instances(Instance):

    def __init__(self, proxy_token):
        self._data_object = self.get_client(proxy_token).servers.list()

    def __iter__(self):
        for item in self._data_object:
            yield item


class DatabaseModelBase(ModelBase):
    _auto_generated_attrs = ['id']

    @classmethod
    def create(cls, **values):
        values['id'] = utils.generate_uuid()
        print values
#        values['created_at'] = utils.utcnow()
        instance = cls(**values).save()
#        instance._notify_fields("create")
        return instance

    def save(self):
        if not self.is_valid():
            raise InvalidModelError(self.errors)
#        self._convert_columns_to_proper_type()
#        self._before_save()
        self['updated_at'] = utils.utcnow()
        LOG.debug("Saving %s: %s" % (self.__class__.__name__, self.__dict__))
        return db.db_api.save(self)

    def __init__(self, **kwargs):
        self.merge_attributes(kwargs)

    def merge_attributes(self, values):
        """dict.update() behaviour."""
        for k, v in values.iteritems():
            self[k] = v



class DBInstance(DatabaseModelBase):
    _data_fields = ['name', 'status']

def persisted_models():
    return {
        'instance': DBInstance,
        }

class InvalidModelError(exception.ReddwarfError):

    message = _("The following values are invalid: %(errors)s")

    def __init__(self, errors, message=None):
        super(InvalidModelError, self).__init__(message, errors=errors)


