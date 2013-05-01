# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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


from novaclient import exceptions as nova_exceptions

from reddwarf.common import exception
from reddwarf.common import wsgi
from reddwarf.common.auth import admin_context
from reddwarf.instance import models as instance_models
from reddwarf.extensions.mgmt.instances import models
from reddwarf.extensions.mgmt.instances import views
from reddwarf.extensions.mgmt.instances.views import DiagnosticsView
from reddwarf.extensions.mgmt.instances.views import HwInfoView
from reddwarf.extensions.mysql import models as mysql_models
from reddwarf.instance.service import InstanceController
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)


class MgmtInstanceController(InstanceController):
    """Controller for instance functionality"""

    @admin_context
    def index(self, req, tenant_id, detailed=False):
        """Return all instances."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a database instance for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        deleted = None
        deleted_q = req.GET.get('deleted', '').lower()
        if deleted_q in ['true']:
            deleted = True
        elif deleted_q in ['false']:
            deleted = False
        try:
            instances = models.load_mgmt_instances(context, deleted=deleted)
        except nova_exceptions.ClientException, e:
            LOG.error(e)
            return wsgi.Result(str(e), 403)

        view_cls = views.MgmtInstancesView
        return wsgi.Result(view_cls(instances, req=req).data(), 200)

    @admin_context
    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        server = models.DetailedMgmtInstance.load(context, id)
        root_history = mysql_models.RootHistory.load(context=context,
                                                     instance_id=id)
        return wsgi.Result(
            views.MgmtInstanceDetailView(
                server,
                req=req,
                root_history=root_history).data(),
            200)

    @admin_context
    def action(self, req, body, tenant_id, id):
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Committing an ACTION against instance %s for tenant '%s'"
                 % (id, tenant_id))
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.MgmtInstance.load(context=context, id=id)
        _actions = {
            'stop': self._action_stop,
            'reboot': self._action_reboot,
            'migrate': self._action_migrate,
            'reset-task-status': self._action_reset_task_status
        }
        selected_action = None
        for key in body:
            if key in _actions:
                if selected_action is not None:
                    msg = _("Only one action can be specified per request.")
                    raise exception.BadRequest(msg)
                selected_action = _actions[key]
            else:
                msg = _("Invalid instance action: %s") % key
                raise exception.BadRequest(msg)

        if selected_action:
            return selected_action(context, instance, body)
        else:
            raise exception.BadRequest(_("Invalid request body."))

    def _action_stop(self, context, instance, body):
        LOG.debug("Stopping MySQL on instance %s." % instance.id)
        instance.stop_db()
        return wsgi.Result(None, 202)

    def _action_reboot(self, context, instance, body):
        LOG.debug("Rebooting instance %s." % instance.id)
        instance.reboot()
        return wsgi.Result(None, 202)

    def _action_migrate(self, context, instance, body):
        LOG.debug("Migrating instance %s." % instance.id)
        instance.migrate()
        return wsgi.Result(None, 202)

    def _action_reset_task_status(self, context, instance, body):
        LOG.debug("Setting Task-Status to NONE on instance %s." %
                  instance.id)
        instance.reset_task_status()
        return wsgi.Result(None, 202)

    @admin_context
    def root(self, req, tenant_id, id):
        """Return the date and time root was enabled on an instance,
        if ever."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing root history for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            server = instance_models.Instance.load(context=context, id=id)
        except exception.ReddwarfError, e:
            LOG.error(e)
            return wsgi.Result(str(e), 404)
        reh = mysql_models.RootHistory.load(context=context, instance_id=id)
        rhv = None
        if reh:
            rhv = views.RootHistoryView(reh.id, enabled=reh.created,
                                        user_id=reh.user)
        else:
            rhv = views.RootHistoryView(id)
        return wsgi.Result(rhv.data(), 200)

    @admin_context
    def hwinfo(self, req, tenant_id, id):
        """Return a single instance hardware info."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing hardware info for instance '%s'") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.MgmtInstance.load(context=context, id=id)

        hwinfo = instance.get_hwinfo()
        return wsgi.Result(HwInfoView(id, hwinfo).data(), 200)

    @admin_context
    def diagnostics(self, req, tenant_id, id):
        """Return a single instance diagnostics."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a instance diagnostics for instance '%s'") % id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.MgmtInstance.load(context=context, id=id)

        diagnostics = instance.get_diagnostics()
        return wsgi.Result(DiagnosticsView(id, diagnostics).data(), 200)
