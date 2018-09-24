# Copyright 2014 Rackspace Hosting
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

Specifically, this forces all various threads of execution to run one at a time
based on when they would have been scheduled using the various eventlet spawn
functions. Because only one thing is running at a given time, it eliminates
race conditions that would normally be present from testing multi-threaded
scenarios. It also means that the simulated time.sleep does not actually have
to sit around for the designated time, which greatly speeds up the time it
takes to run the tests.

Event Simulator Overview
========================

We use this to simulate all the threads of Trove running.
i.e. (api,taskmanager,proboscis tests). All the services end
up sleeping and having to wait for something to happen at times.

Monkey Patching Methods
-----------------------
We monkey patch a few methods to make this happen.

A few sleep methods with a fake_sleep.
* time.sleep
* eventlet.sleep
* greenthread.sleep

A few spawn methods with a fake_spawn
* eventlet.spawn_after
* eventlet.spawn_n

Raise an error if you try this one.
* eventlet.spawn

Replace the poll_until with a fake_poll_until.

Coroutine Object
----------------

There is a Coroutine object here that mimics the behavior of a thread.
It takes in a function with args and kwargs and executes it. If at any
point that method calls time.sleep(seconds) then the event simulator will
put that method on the stack of threads and run the fake_sleep method
that will then iterate over all the threads in the stack updating the time
they still need to sleep. Then as the threads hit the end of their sleep
time period they will continue to execute.

fake_threads
------------

One thing to note here is the idea of a stack of threads being kept in
fake_threads list. Any new thread created is added to this stack.

A fake_thread attributes:

fake_thread = {
    'sleep': time_from_now_in_seconds,
    'greenlet': Coroutine(method_to_execute),
    'name': str(func)
}

'sleep' is the time it should wait to execute this method.
'greenlet' is the thread object
'name' is the unique name of the thread to track

main_loop Method
----------------

The main_loop method is a loop that runs forever waiting on all the
threads to complete while running pulse every 0.1 seconds. This is the
key to simulated the threads quickly. We are pulsing every 0.1
seconds looking to make sure there are no threads just waiting around for
no reason rather than waiting a full second to respond.

pulse Method
------------

The pulse method is going through the stack(list) of threads looking for
the next thread to execute while updating the 'sleep' time and the if
the 'sleep' time is <=0 then it will run this thread until it calls for
another time.sleep.

If the method/thread running calls time.sleep for what ever reason then
the thread's 'sleep' parameter is updated to the new 'next_sleep_time'.

If the method/thread running completes without calling time.sleep because it
finished all work needed to be done then there the 'next_sleep_time' is set
to None and the method/thread is deleted from the stack(list) of threads.
"""
import eventlet
from eventlet.event import Event
from eventlet.semaphore import Semaphore
from eventlet import spawn as true_spawn


class Coroutine(object):
    """
    This class simulates a coroutine, which is ironic, as greenlet actually
    *is* a coroutine. But trying to use greenlet here gives nasty results
    since eventlet thoroughly monkey-patches things, making it difficult
    to run greenlet on its own.

    Essentially think of this as a wrapper for eventlet's threads which has a
    run and sleep function similar to old school coroutines, meaning it won't
    start until told and when asked to sleep it won't wake back up without
    permission.
    """

    ALL = []

    def __init__(self, func, *args, **kwargs):
        self.my_sem = Semaphore(0)   # This is held by the thread as it runs.
        self.caller_sem = None
        self.dead = False
        started = Event()
        self.id = 5
        self.ALL.append(self)

        def go():
            self.id = eventlet.corolocal.get_ident()
            started.send(True)
            self.my_sem.acquire(blocking=True, timeout=None)
            try:
                func(*args, **kwargs)
            # except Exception as e:
            #     print("Exception in coroutine! %s" % e)
            finally:
                self.dead = True
                self.caller_sem.release()  # Relinquish control back to caller.
                for i in range(len(self.ALL)):
                    if self.ALL[i].id == self.id:
                        del self.ALL[i]
                        break

        true_spawn(go)
        started.wait()

    @classmethod
    def get_current(cls):
        """Finds the coroutine associated with the thread which calls it."""
        return cls.get_by_id(eventlet.corolocal.get_ident())

    @classmethod
    def get_by_id(cls, id):
        for cr in cls.ALL:
            if cr.id == id:
                return cr
        raise RuntimeError("Coroutine with id %s not found!" % id)

    def sleep(self):
        """Puts the coroutine to sleep until run is called again.

        This should only be called by the thread which owns this object.
        """
        # Only call this from its own thread.
        assert eventlet.corolocal.get_ident() == self.id
        self.caller_sem.release()  # Relinquish control back to caller.
        self.my_sem.acquire(blocking=True, timeout=None)

    def run(self):
        """Starts up the thread. Should be called from a different thread."""
        # Don't call this from the thread which it represents.
        assert eventlet.corolocal.get_ident() != self.id
        self.caller_sem = Semaphore(0)
        self.my_sem.release()
        self.caller_sem.acquire()  # Wait for it to finish.

# Main global thread to run.
main_greenlet = None

# Stack of threads currently running or sleeping
fake_threads = []

# Allow a sleep method to be called at least this number of times before
# raising an error that there are not other active threads waiting to run.
allowable_empty_sleeps = 1
sleep_allowance = allowable_empty_sleeps


def other_threads_are_active():
    """Returns True if concurrent activity is being simulated.

    Specifically, this means there is a fake thread in action other than the
    "pulse" thread and the main test thread.
    """
    return len(fake_threads) >= 2


def fake_sleep(time_to_sleep):
    """Simulates sleep.

    Puts the coroutine which calls it to sleep. If a coroutine object is not
    associated with the caller this will fail.
    """
    if time_to_sleep:
        global sleep_allowance
        sleep_allowance -= 1
        if not other_threads_are_active():
            if sleep_allowance < -1:
                raise RuntimeError("Sleeping for no reason.")
            else:
                return  # Forgive the thread for calling this for one time.
        sleep_allowance = allowable_empty_sleeps

    cr = Coroutine.get_current()
    for ft in fake_threads:
        if ft['greenlet'].id == cr.id:
            ft['next_sleep_time'] = time_to_sleep

    cr.sleep()


def fake_poll_until(retriever, condition=lambda value: value,
                    sleep_time=1, time_out=0):
    """Fakes out poll until."""
    from trove.common import exception
    slept_time = 0
    while True:
        resource = retriever()
        if condition(resource):
            return resource
        fake_sleep(sleep_time)
        slept_time += sleep_time
        if time_out and slept_time >= time_out:
                raise exception.PollTimeOut()


def run_main(func):
    """Runs the given function as the initial thread of the event simulator."""
    global main_greenlet
    main_greenlet = Coroutine(main_loop)
    fake_spawn(0, func)
    main_greenlet.run()


def main_loop():
    """The coroutine responsible for calling each "fake thread."

    The Coroutine which calls this is the only one that won't end up being
    associated with the fake_threads list. The reason is this loop needs to
    wait on whatever thread is running, meaning it has to be a Coroutine as
    well.
    """
    while len(fake_threads) > 0:
        pulse(0.1)


def fake_spawn_n(func, *args, **kw):
    fake_spawn(0, func, *args, **kw)


def fake_spawn(time_from_now_in_seconds, func, *args, **kw):
    """Fakes eventlet's spawn function by adding a fake thread."""
    def thread_start():
        # fake_sleep(time_from_now_in_seconds)
        return func(*args, **kw)

    cr = Coroutine(thread_start)
    fake_threads.append({'sleep': time_from_now_in_seconds,
                         'greenlet': cr,
                         'name': str(func)})


def pulse(seconds):
    """
    Runs the event simulator for the amount of simulated time denoted by
    "seconds".
    """
    index = 0
    while index < len(fake_threads):
        t = fake_threads[index]
        t['sleep'] -= seconds
        if t['sleep'] <= 0:
            t['sleep'] = 0
            t['next_sleep_time'] = None
            t['greenlet'].run()
            sleep_time = t['next_sleep_time']
            if sleep_time is None or isinstance(sleep_time, tuple):
                del fake_threads[index]
                index -= 1
            else:
                t['sleep'] = sleep_time
        index += 1


def wait_until_all_activity_stops():
    """In fake mode, wait for all simulated events to chill out.

    This can be useful in situations where you need simulated activity (such
    as calls running in TaskManager) to "bleed out" and finish before running
    another test.

    """
    if main_greenlet is None:
        return
    while other_threads_are_active():
        fake_sleep(1)


def monkey_patch():
    """
    Changes global functions such as time.sleep, eventlet.spawn* and others
    to their event_simulator equivalents.
    """
    import time
    time.sleep = fake_sleep
    import eventlet
    from eventlet import greenthread
    eventlet.sleep = fake_sleep
    greenthread.sleep = fake_sleep
    eventlet.spawn_after = fake_spawn

    def raise_error():
        raise RuntimeError("Illegal operation!")

    eventlet.spawn_n = fake_spawn_n
    eventlet.spawn = raise_error
    from trove.common import utils
    utils.poll_until = fake_poll_until
