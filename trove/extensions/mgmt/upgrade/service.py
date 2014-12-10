# Copyright 2014 OpenStack Foundation
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
from trove.common.auth import admin_context
from trove.extensions.mgmt.upgrade.models import UpgradeMessageSender
from trove.openstack.common import log as logging
from trove.common.i18n import _
import trove.common.apischema as apischema


LOG = logging.getLogger(__name__)


class UpgradeController(wsgi.Controller):
    """
    Controller for guest agent upgrade
    """
    schemas = apischema.upgrade

    @admin_context
    def create(self, req, body, tenant_id, instance_id):
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Sending upgrade notification"))
        LOG.debug(_("Admin tenant_id: %s") % tenant_id)

        context = req.environ.get(wsgi.CONTEXT_KEY)
        upgrade = body['upgrade']

        instance_version = upgrade.get('instance_version')
        location = upgrade.get('location')
        metadata = upgrade.get('metadata')

        send = UpgradeMessageSender.create(
            context, instance_id, instance_version, location, metadata)

        send()
        return wsgi.Result(None, 202)
