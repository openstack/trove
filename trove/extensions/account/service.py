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

import trove.common.apischema as apischema
from trove.common.auth import admin_context
from trove.common import wsgi
from trove.extensions.account import models
from trove.extensions.account import views

LOG = logging.getLogger(__name__)


class AccountController(wsgi.Controller):
    """Controller for account functionality."""
    schemas = apischema.account

    @admin_context
    def show(self, req, tenant_id, id):
        """Return a account and instances associated with a single account."""
        LOG.info("req : '%s'\n\n", req)
        LOG.info("Showing account information for '%(account)s' "
                 "to '%(tenant)s'", {'account': id, 'tenant': tenant_id})

        context = req.environ[wsgi.CONTEXT_KEY]
        account = models.Account.load(context, id)
        return wsgi.Result(views.AccountView(account).data(), 200)

    @admin_context
    def index(self, req, tenant_id):
        """Return a list of all accounts with non-deleted instances."""
        LOG.info("req : '%s'\n\n", req)
        LOG.info("Showing all accounts with instances for '%s'", tenant_id)
        accounts_summary = models.AccountsSummary.load()
        return wsgi.Result(views.AccountsView(accounts_summary).data(), 200)
