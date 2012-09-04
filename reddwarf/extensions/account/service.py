# Copyright 2012 OpenStack LLC.
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

import logging

from novaclient import exceptions as nova_exceptions

from reddwarf.common import exception

from reddwarf.common import wsgi
from reddwarf.common.auth import admin_context
from reddwarf.common.remote import create_nova_client
from reddwarf.extensions.account import models
from reddwarf.extensions.account import views
from reddwarf.instance.models import DBInstance


LOG = logging.getLogger(__name__)


class AccountController(wsgi.Controller):
    """Controller for account functionality"""

    @admin_context
    def show(self, req, tenant_id, id):
        """Return a account and instances associated with a single account."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing account information for '%s' to '%s'")
                  % (id, tenant_id))

        context = req.environ[wsgi.CONTEXT_KEY]
        account = models.Account.load(context, id)
        return wsgi.Result(views.AccountView(account).data(), 200)

    @admin_context
    def index(self, req, tenant_id):
        """Return a list of all accounts with non-deleted instances."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing all accounts with instances for '%s'") % tenant_id)
        accounts_summary = models.AccountsSummary.load()
        return wsgi.Result(views.AccountsView(accounts_summary).data(), 200)
