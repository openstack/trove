# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack LLC.
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

"""Model classes that form the core of instance flavor functionality."""

import logging

from reddwarf import db

from novaclient import exceptions as nova_exceptions
from novaclient.v1_1.client import Client
from reddwarf.common import config
from reddwarf.common import exception as rd_exceptions
from reddwarf.common import utils
from reddwarf.common.models import NovaRemoteModelBase

CONFIG = config.Config
LOG = logging.getLogger('reddwarf.database.models')


class Flavor(NovaRemoteModelBase):

    _data_fields = ['id', 'links', 'name', 'ram']

    def __init__(self, flavor=None, context=None, flavor_id=None):
        if flavor:
            self._data_object = flavor
            return
        if flavor_id and context:
            try:
                client = self.get_client(context)
                self._data_object = client.flavors.get(flavor_id)
            except nova_exceptions.NotFound, e:
                raise rd_exceptions.NotFound(uuid=flavor_id)
            except nova_exceptions.ClientException, e:
                raise rd_exceptions.ReddwarfError(str(e))
            # Now modify the links
            return
        msg = ("Flavor is not defined, and"
               " context and flavor_id were not specified.")
        raise InvalidModelError(msg)

    @property
    def links(self):
        return self._build_links()

    def _build_links(self):
        # TODO(ed-): Fix this URL: Change the endpoint, port, auth version,
        # and the presence of the tenant id.
        return self._data_object.links

class Flavors(NovaRemoteModelBase):
    # Flavors HASA list of Flavor objects.

    def __init__(self, context):
        nova_flavors = self.get_client(context).flavors.list()
        self._data_object = [Flavor(flavor=item).data() for item in nova_flavors]

    def __iter__(self):
        for item in self._data_object:
            yield item

