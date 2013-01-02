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

from novaclient import exceptions as nova_exceptions
from reddwarf.common import cfg
from reddwarf.openstack.common import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def authorize(context):
    if not context.is_admin:
        raise nova_exceptions.Forbidden(403, "Forbidden")


def get_event_spawer():
    if CONF.fake_mode_events == "simulated":
        return event_simulator
    else:
        return eventlet_spawner


pending_events = []
sleep_entrance_count = 0


def eventlet_spawner(time_from_now_in_seconds, func):
    """Uses eventlet to spawn events."""
    import eventlet
    eventlet.spawn_after(time_from_now_in_seconds, func)


def event_simulator(time_from_now_in_seconds, func):
    """Fakes events without doing any actual waiting."""
    pending_events.append({"time": time_from_now_in_seconds, "func": func})


def event_simulator_sleep(time_to_sleep):
    """Simulates waiting for an event."""
    global sleep_entrance_count
    sleep_entrance_count += 1
    time_to_sleep = float(time_to_sleep)
    global pending_events
    while time_to_sleep > 0:
        itr_sleep = 0.5
        for i in range(len(pending_events)):
            event = pending_events[i]
            event["time"] = event["time"] - itr_sleep
            if event["func"] is not None and event["time"] < 0:
                # Call event, but first delete it so this function can be
                # reentrant.
                func = event["func"]
                event["func"] = None
                try:
                    func()
                except Exception as e:
                    LOG.exception("Simulated event error.")

        time_to_sleep -= itr_sleep
    sleep_entrance_count -= 1
    if sleep_entrance_count < 1:
        # Clear out old events
        pending_events = [event for event in pending_events
                          if event["func"] is not None]
