#!/usr/bin/env python

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

import gettext
import sys


gettext.install('trove', unicode=1)


from trove.common import cfg
from trove.common import debug_utils
from trove.openstack.common import log as logging
from trove.common import wsgi
from trove.db import get_db_api


CONF = cfg.CONF


def main():
    cfg.parse_args(sys.argv)
    logging.setup(None)

    debug_utils.setup()

    get_db_api().configure_db(CONF)
    conf_file = CONF.find_file(CONF.api_paste_config)
    launcher = wsgi.launch('trove', CONF.bind_port or 8779, conf_file,
                           workers=CONF.trove_api_workers)
    launcher.wait()
