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
Standard openstack.common.rpc.impl_fake with nonblocking cast
"""

from trove.openstack.common.rpc.impl_fake import *


original_cast = cast


def non_blocking_cast(*args, **kwargs):
    eventlet.spawn_n(original_cast, *args, **kwargs)


cast = non_blocking_cast
