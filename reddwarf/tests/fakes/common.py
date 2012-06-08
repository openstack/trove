# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Common code to help in faking the models."""

import time
import stubout

from novaclient import exceptions as nova_exceptions


def authorize(context):
    if not context.user in ['radmin', 'Boss']:
        raise nova_exceptions.Forbidden(403, "Forbidden")


class EventSimulator(object):
    """Simulates a resource that changes over time.

    Has a list of events which execute in real time to change state.
    The implementation is very dumb; if you give it two events at once the
    last one wins.

    """

    @staticmethod
    def add_event(time_from_now_in_seconds, func):
        if time_from_now_in_seconds <= 0:
            func()
        else:
            import eventlet
            eventlet.spawn_after(time_from_now_in_seconds, func)
