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

"""
Simple class that stores security context information in the web request.

Projects should subclass this class if they wish to enhance the request
context or provide additional information in their specific WSGI pipeline.
"""


from oslo_context import context
from oslo_log import log as logging
from oslo_utils import reflection

from trove.common.i18n import _
from trove.common import local
from trove.common.serializable_notification import SerializableNotification

LOG = logging.getLogger(__name__)


class TroveContext(context.RequestContext):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """
    def __init__(self, limit=None, marker=None, service_catalog=None,
                 user_identity=None, instance_id=None, timeout=None,
                 **kwargs):
        self.limit = limit
        self.marker = marker
        self.service_catalog = service_catalog
        self.user_identity = user_identity
        self.instance_id = instance_id
        self.timeout = timeout
        super(TroveContext, self).__init__(**kwargs)

        if not hasattr(local.store, 'context'):
            self.update_store()

    def to_dict(self):
        parent_dict = super(TroveContext, self).to_dict()
        parent_dict.update({'limit': self.limit,
                            'marker': self.marker,
                            'service_catalog': self.service_catalog
                            })
        if hasattr(self, 'notification'):
            serialized = SerializableNotification.serialize(self,
                                                            self.notification)
            parent_dict['trove_notification'] = serialized
        return parent_dict

    def update_store(self):
        local.store.context = self

    @classmethod
    def _remove_incompatible_context_args(cls, values):
        realvalues = {}

        args = (reflection.get_callable_args(context.RequestContext.__init__) +
                reflection.get_callable_args(TroveContext.__init__))

        for dict_key in values.keys():
            if dict_key in args:
                realvalues[dict_key] = values.get(dict_key)
            else:
                LOG.warning(_("Argument being removed before instantiating "
                              "TroveContext object - %(key)s = %(value)s"),
                            {'key': dict_key, 'value': values.get(dict_key)})

        return realvalues

    @classmethod
    def from_dict(cls, values):
        n_values = values.pop('trove_notification', None)
        values = cls._remove_incompatible_context_args(values)
        context = cls(**values)
        if n_values:
            context.notification = SerializableNotification.deserialize(
                context, n_values)
        return context
