# Copyright (c) 2012 OpenStack, LLC.
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
Test utility for RPC checks.

Functionality to check for rabbit here depends on having rabbit running on
the same machine as the tests, so that the rabbitmqctl commands will function.
The functionality is turned on or off by the test config "rabbit_runs_locally".

"""

import re

from trove.tests.config import CONFIG
from services import start_proc


if CONFIG.values.get('rabbit_runs_locally', False) == True:

    DIRECT_ACCESS = True

    class Rabbit(object):

        def declare_queue(self, topic):
            """Call this to declare a queue from Python."""
            #from trove.rpc.impl_kombu import Connection
            from trove.openstack.common.rpc import create_connection
            with create_connection() as conn:
                consumer = conn.declare_topic_consumer(topic=topic)

        def get_queue_items(self, queue_name):
            """Determines if the queue exists and if so the message count.

            If the queue exists the return value is an integer, otherwise
            its None.

            Be careful because queue_name is used in a regex and can't have
            any unescaped characters.

            """
            proc = start_proc(["/usr/bin/sudo", "rabbitmqctl", "list_queues"],
                              shell=False)
            for line in iter(proc.stdout.readline, ""):
                print("LIST QUEUES:" + line)
                m = re.search("""%s\s+([0-9]+)""" % queue_name, line)
                if m:
                    return int(m.group(1))
            return None

        @property
        def is_alive(self):
            """Calls list_queues, should fail."""
            try:
                stdout, stderr = self.run(0, "rabbitmqctl", "list_queues")
                for lines in stdout, stderr:
                    for line in lines:
                        if "no_exists" in line:
                            return False
                return True
            except Exception:
                return False

        def reset(self):
            out, err = self.run(0, "rabbitmqctl", "reset")
            print(out)
            print(err)

        def run(self, check_exit_code, *cmd):
            cmds = ["/usr/bin/sudo"] + list(cmd)
            proc = start_proc(cmds)
            lines = proc.stdout.readlines()
            err_lines = proc.stderr.readlines()
            return lines, err_lines

        def start(self):
            print("Calling rabbitmqctl start_app")
            out = self.run(0, "rabbitmqctl", "start_app")
            print(out)
            out, err = self.run(0, "rabbitmqctl", "change_password", "guest",
                                CONFIG.values['rabbit_password'])
            print(out)
            print(err)

        def stop(self):
            print("Calling rabbitmqctl stop_app")
            out = self.run(0, "rabbitmqctl", "stop_app")
            print(out)

else:

    DIRECT_ACCESS = False

    class Rabbit(object):

        def __init__(self):
            raise RuntimeError("rabbit_runs_locally is set to False in the "
                               "test config, so this test cannot be run.")

