# Copyright 2016 Tesora, Inc
#
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

from trove.common import wsgi
from trove.volume_type import models
from trove.volume_type import views


class VolumeTypesController(wsgi.Controller):
    """A controller for the Cinder Volume Types functionality."""

    def show(self, req, tenant_id, id):
        """Return a single volume type."""
        context = req.environ[wsgi.CONTEXT_KEY]
        volume_type = models.VolumeType.load(id, context=context)
        return wsgi.Result(views.VolumeTypeView(volume_type, req).data(), 200)

    def index(self, req, tenant_id):
        """Return all volume types."""
        context = req.environ[wsgi.CONTEXT_KEY]
        volume_types = models.VolumeTypes(context=context)
        return wsgi.Result(views.VolumeTypesView(volume_types,
                                                 req).data(), 200)
