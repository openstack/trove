# Copyright (c) 2011 OpenStack, LLC.
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

import os

from proboscis import test
from proboscis.asserts import fail
from tests.util.services import Service
from trove.tests.config import CONFIG


def dbaas_url():
    return str(CONFIG.values.get("dbaas_url"))


def nova_url():
    return str(CONFIG.values.get("nova_client")['url'])


class Daemon(object):
    """Starts a daemon."""

    def __init__(self, alternate_path=None, conf_file_name=None,
                 extra_cmds=None, service_path_root=None, service_path=None):
        # The path to the daemon bin if the other one doesn't work.
        self.alternate_path = alternate_path
        self.extra_cmds = extra_cmds or []
        # The name of a test config value which points to a conf file.
        self.conf_file_name = conf_file_name
        # The name of a test config value, which is inserted into the service_path.
        self.service_path_root = service_path_root
        # The first path to the daemon bin we try.
        self.service_path = service_path or "%s"

    def run(self):
        # Print out everything to make it
        print("Looking for config value %s..." % self.service_path_root)
        print(CONFIG.values[self.service_path_root])
        path = self.service_path % CONFIG.values[self.service_path_root]
        print("Path = %s" % path)
        if not os.path.exists(path):
            path = self.alternate_path
        if path is None:
            fail("Could not find path to %s" % self.service_path_root)
        conf_path = str(CONFIG.values[self.conf_file_name])
        cmds = CONFIG.python_cmd_list() + [path] + self.extra_cmds + \
               [conf_path]
        print("Running cmds: %s" % cmds)
        self.service = Service(cmds)
        if not self.service.is_service_alive():
            self.service.start()
