# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

"""
Simulates time itself to make the fake mode tests run even faster.
"""

from proboscis.asserts import fail
from trove.openstack.common import log as logging
from trove.common import exception


LOG = logging.getLogger(__name__)

allowable_empty_sleeps = 0
pending_events = []
sleep_entrance_count = 0


def event_simulator_spawn_after(time_from_now_in_seconds, func, *args, **kw):
    """Fakes events without doing any actual waiting."""
    def __cb():
        func(*args, **kw)
    pending_events.append({"time": time_from_now_in_seconds, "func": __cb})


def event_simulator_spawn(func, *args, **kw):
    event_simulator_spawn_after(0, func, *args, **kw)


def event_simulator_sleep(time_to_sleep):
    """Simulates waiting for an event.

    This is used to monkey patch the sleep methods, so that no actually waiting
    occurs but functions which would have run as threads are executed.

    This function will also raise an assertion failure if there were no pending
    events ready to run. If this happens there are two possibilities:
        1. The test code (or potentially code in Trove task manager) is
           sleeping even though no action is taking place in
           another thread.
        2. The test code (or task manager code) is sleeping waiting for a
           condition that will never be met because the thread it was waiting
           on experienced an error or did not finish successfully.

    A good example of this second case is when a bug in task manager causes the
    create instance method to fail right away, but the test code tries to poll
    the instance's status until it gets rate limited. That makes finding the
    real error a real hassle. Thus it makes more sense to raise an exception
    whenever the app seems to be napping for no reason.

    """
    global pending_events
    global allowable_empty_sleeps
    if len(pending_events) == 0:
        allowable_empty_sleeps -= 1
        if allowable_empty_sleeps < 0:
            fail("Trying to sleep when no events are pending.")

    global sleep_entrance_count
    sleep_entrance_count += 1
    time_to_sleep = float(time_to_sleep)

    run_once = False  # Ensure simulator runs even if the sleep time is zero.
    while not run_once or time_to_sleep > 0:
        run_once = True
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
                except Exception:
                    LOG.exception("Simulated event error.")
        time_to_sleep -= itr_sleep
    sleep_entrance_count -= 1
    if sleep_entrance_count < 1:
        # Clear out old events
        pending_events = [event for event in pending_events
                          if event["func"] is not None]


def fake_poll_until(retriever, condition=lambda value: value,
                    sleep_time=1, time_out=None):
    """Retrieves object until it passes condition, then returns it.

    If time_out_limit is passed in, PollTimeOut will be raised once that
    amount of time is eclipsed.

    """
    slept_time = 0
    while True:
        resource = retriever()
        if condition(resource):
            return resource
        event_simulator_sleep(sleep_time)
        slept_time += sleep_time
        if time_out and slept_time >= time_out:
                raise exception.PollTimeOut()


def monkey_patch():
    import time
    time.sleep = event_simulator_sleep
    import eventlet
    from eventlet import greenthread
    eventlet.sleep = event_simulator_sleep
    greenthread.sleep = event_simulator_sleep
    eventlet.spawn_after = event_simulator_spawn_after
    eventlet.spawn_n = event_simulator_spawn
    eventlet.spawn = NotImplementedError
    from trove.common import utils
    utils.poll_until = fake_poll_until
