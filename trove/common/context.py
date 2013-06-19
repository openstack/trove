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

"""
Simple class that stores security context information in the web request.

Projects should subclass this class if they wish to enhance the request
context or provide additional information in their specific WSGI pipeline.
"""

from trove.openstack.common import context
from trove.openstack.common import local
from trove.common import utils


class TroveContext(context.RequestContext):

    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """

    def __init__(self, **kwargs):
        self.limit = kwargs.get('limit')
        if 'limit' in kwargs:
            del kwargs['limit']
        self.marker = kwargs.get('marker')
        if 'marker' in kwargs:
            del kwargs['marker']
        super(TroveContext, self).__init__(**kwargs)

        if not hasattr(local.store, 'context'):
            self.update_store()

    def to_dict(self):
        parent_dict = super(TroveContext, self).to_dict()
        parent_dict.update({'limit': self.limit,
                            'marker': self.marker
                            })
        return parent_dict

    def update_store(self):
        local.store.context = self

    @classmethod
    def from_dict(cls, values):
        return cls(**values)
