# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from oslo_service import loopingcall


def build_polling_task(retriever, condition=lambda value: value,
                       sleep_time=1, time_out=0, initial_delay=0):
    """Run a function in a loop with backoff on error.

    The condition function runs based on the retriever function result.
    """

    def poll_and_check():
        obj = retriever()
        if condition(obj):
            raise loopingcall.LoopingCallDone(retvalue=obj)

    call = loopingcall.BackOffLoopingCall(f=poll_and_check)
    return call.start(initial_delay=initial_delay,
                      starting_interval=sleep_time,
                      max_interval=30, timeout=time_out)


def poll_until(retriever, condition=lambda value: value,
               sleep_time=3, time_out=0, initial_delay=0):
    """Retrieves object until it passes condition, then returns it.

    If time_out_limit is passed in, PollTimeOut will be raised once that
    amount of time is eclipsed.

    """
    task = build_polling_task(retriever, condition=condition,
                              sleep_time=sleep_time, time_out=time_out,
                              initial_delay=initial_delay)
    return task.wait()
