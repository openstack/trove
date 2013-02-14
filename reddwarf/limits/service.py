# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack LLC
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from reddwarf.common import wsgi as base_wsgi
from reddwarf.common.limits import LimitsTemplate
from reddwarf.limits import views
from reddwarf.openstack.common import wsgi


class LimitsController(base_wsgi.Controller):
    """
    Controller for accessing limits in the OpenStack API.
    Note: this is a little different than how other controllers are implemented
    """

    @base_wsgi.serializers(xml=LimitsTemplate)
    def index(self, req, tenant_id):
        """
        Return all global and rate limit information.
        """
        context = req.environ[base_wsgi.CONTEXT_KEY]

        #
        # TODO: hook this in later
        #quotas = QUOTAS.get_project_quotas(context, context.project_id,
        #                                   usages=False)
        #abs_limits = dict((k, v['limit']) for k, v in quotas.items())
        abs_limits = {}
        rate_limits = req.environ.get("reddwarf.limits", [])

        builder = self._get_view_builder(req)
        return builder.build(rate_limits, abs_limits)

    def _get_view_builder(self, req):
        return views.ViewBuilder()
