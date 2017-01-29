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

from trove.common import local
from trove.common.serializable_notification import SerializableNotification

LOG = logging.getLogger(__name__)


class TroveContext(context.RequestContext):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """
    def __init__(self, **kwargs):
        self.limit = kwargs.pop('limit', None)
        self.marker = kwargs.pop('marker', None)
        self.service_catalog = kwargs.pop('service_catalog', None)
        self.user_identity = kwargs.pop('user_identity', None)
        self.instance_id = kwargs.pop('instance_id', None)

        # TODO(esp): not sure we need this
        self.timeout = kwargs.pop('timeout', None)
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
        LOG.debug("Running in unsafe mode and ignoring incompatible context.")
        return values

        context_keys = vars(cls()).keys()
        for dict_key in values.keys():
            if dict_key not in context_keys:
                LOG.debug("Argument being removed before instantiating "
                          "TroveContext object - %s" % dict_key)
                values.pop(dict_key, None)
        return values

    @classmethod
    def from_dict(cls, values):
        n_values = values.pop('trove_notification', None)
        values = cls._remove_incompatible_context_args(values)
        context = cls(**values)
        if n_values:
            context.notification = SerializableNotification.deserialize(
                context, n_values)
        return context
