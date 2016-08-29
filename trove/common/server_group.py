# Copyright 2016 Tesora, Inc.
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
#

import six

from oslo_log import log as logging

from trove.common.i18n import _
from trove.common.remote import create_nova_client


LOG = logging.getLogger(__name__)


class ServerGroup(object):

    @classmethod
    def load(cls, context, compute_id):
        client = create_nova_client(context)
        server_group = None
        try:
            for sg in client.server_groups.list():
                if compute_id in sg.members:
                    server_group = sg
        except Exception:
            LOG.exception(_("Could not load server group for compute %s") %
                          compute_id)
        return server_group

    @classmethod
    def create(cls, context, locality, name_suffix):
        client = create_nova_client(context)
        server_group_name = "%s_%s" % ('locality', name_suffix)
        server_group = client.server_groups.create(
            name=server_group_name, policies=[locality])
        LOG.debug("Created '%s' server group called %s (id: %s)." %
                  (locality, server_group_name, server_group.id))

        return server_group

    @classmethod
    def delete(cls, context, server_group, force=False):
        # Only delete the server group if we're the last member in it, or if
        # it has no members
        if server_group:
            if force or len(server_group.members) <= 1:
                client = create_nova_client(context)
                client.server_groups.delete(server_group.id)
                LOG.debug("Deleted server group %s." % server_group.id)
            else:
                LOG.debug("Skipping delete of server group %s (members: %s)." %
                          (server_group.id, server_group.members))

    @classmethod
    def convert_to_hint(cls, server_group, hints=None):
        if server_group:
            hints = hints or {}
            hints["group"] = server_group.id
        return hints

    @classmethod
    def build_scheduler_hint(cls, context, locality, name_suffix):
        scheduler_hint = None
        if locality:
            # Build the scheduler hint, but only if locality's a string
            if isinstance(locality, six.string_types):
                server_group = cls.create(
                    context, locality, name_suffix)
                scheduler_hint = cls.convert_to_hint(
                    server_group)
            else:
                # otherwise assume it's already in hint form (i.e. a dict)
                scheduler_hint = locality
        return scheduler_hint

    @classmethod
    def get_locality(cls, server_group):
        locality = None
        if server_group:
            locality = server_group.policies[0]
        return locality
