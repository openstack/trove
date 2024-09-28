# Copyright 2015 Tesora, Inc.
#
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

# This file implements eventlet monkey patching according to the OpenStack
# guidelines and best practices found at (note the multi-line URL)
# http://specs.openstack.org/openstack/
#     openstack-specs/specs/eventlet-best-practices.html
#
# It is not safe to leave monkey patching till later.

import os

if not os.environ.get('NO_EVENTLET_MONKEYPATCH'):
    import eventlet
    eventlet.monkey_patch(all=True)
