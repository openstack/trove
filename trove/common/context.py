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

from trove.openstack.common import local


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
        return parent_dict

    def update_store(self):
        local.store.context = self

    @classmethod
    def from_dict(cls, values):
        return cls(**values)
