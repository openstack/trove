# Copyright 2012 OpenStack Foundation
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


from oslo_log import log as logging

from trove.common import exception
from trove.common.i18n import _
from trove.common import wsgi
from trove.extensions.mgmt.host import models

LOG = logging.getLogger(__name__)


class HostInstanceController(wsgi.Controller):
    """Controller for all instances on specific hosts."""

    def action(self, req, body, tenant_id, host_id):
        LOG.info(_("Committing an ACTION against host %(host_id)s for "
                   "tenant '%(tenant_id)s'\n"
                   "req : '%(req)s'\n\n") % {"req": req, "host_id": host_id,
                                             "tenant_id": tenant_id})

        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        host = models.DetailedHost.load(context, host_id)
        _actions = {'update': self._action_update}
        selected_action = None
        for key in body:
            if key in _actions:
                if selected_action is not None:
                    msg = _("Only one action can be specified per request.")
                    raise exception.BadRequest(msg)
                selected_action = _actions[key]
            else:
                msg = _("Invalid host action: %s") % key
                raise exception.BadRequest(msg)

        if selected_action:
            return selected_action(context, host, body)
        else:
            raise exception.BadRequest(_("Invalid request body."))

    def _action_update(self, context, host, body):
        LOG.debug("Updating all instances for host: %s" % host.name)
        host.update_all(context)
        return wsgi.Result(None, 202)
