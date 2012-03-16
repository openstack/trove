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

from reddwarf.common import config
from novaclient.v1_1.client import Client

CONFIG = config.Config
LOG = logging.getLogger('reddwarf.database.models')


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

    def __eq__(self, other):
        if not hasattr(other, 'id'):
            return False
        return type(other) == type(self) and other.id == self.id

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return self.id.__hash__()


class NovaRemoteModelBase(ModelBase):

    # This should be set by the remote model during init time
    # The data() method will be using this
    _data_object = None

    @classmethod
    def get_client(cls, context):
        # Quite annoying but due to a paste config loading bug.
        # TODO(hub-cap): talk to the openstack-common people about this
        PROXY_ADMIN_USER = CONFIG.get('reddwarf_proxy_admin_user', 'admin')
        PROXY_ADMIN_PASS = CONFIG.get('reddwarf_proxy_admin_pass',
                                      '3de4922d8b6ac5a1aad9')
        PROXY_ADMIN_TENANT_NAME = CONFIG.get(
                                        'reddwarf_proxy_admin_tenant_name',
                                        'admin')
        PROXY_AUTH_URL = CONFIG.get('reddwarf_auth_url',
                                    'http://0.0.0.0:5000/v2.0')
        REGION_NAME = CONFIG.get('nova_region_name', 'RegionOne')
        SERVICE_TYPE = CONFIG.get('nova_service_type', 'compute')
        SERVICE_NAME = CONFIG.get('nova_service_name', 'Compute Service')

        #TODO(cp16net) need to fix this proxy_tenant_id
        client = Client(PROXY_ADMIN_USER, PROXY_ADMIN_PASS,
            PROXY_ADMIN_TENANT_NAME, PROXY_AUTH_URL,
            proxy_tenant_id="reddwarf",
            proxy_token=context.auth_tok,
            region_name=REGION_NAME,
            service_type=SERVICE_TYPE,
            service_name=SERVICE_NAME)
        client.authenticate()
        return client

    def _data_item(self, data_object):
        data_fields = self._data_fields + self._auto_generated_attrs
        return dict([(field, getattr(data_object, field))
                     for field in data_fields])

    # data magic that will allow for a list of _data_object or a single item
    # if the object is a list, it will turn it into a list of hash's again
    def data(self, **options):
        if self._data_object is None:
            raise LookupError("data object is None")
        if isinstance(self._data_object, list):
            return [self._data_item(item) for item in self._data_object]
        else:
            return self._data_item(self._data_object)
