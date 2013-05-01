# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

"""
Handles all processes within the Guest VM, considering it as a Platform

The :py:class:`GuestManager` class is a :py:class:`nova.manager.Manager` that
handles RPC calls relating to Platform specific operations.

**Related Flags**

"""

import os
import re
import time
import uuid

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy import exc
from sqlalchemy import interfaces
from sqlalchemy.sql.expression import text

from reddwarf import db
from reddwarf.common.exception import ProcessExecutionError
from reddwarf.common import cfg
from reddwarf.common import utils
from reddwarf.guestagent import query
from reddwarf.guestagent.db import models
from reddwarf.guestagent import pkg
from reddwarf.instance import models as rd_models
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)

SERVICE_REGISTRY = {
    'mysql': 'reddwarf.guestagent.manager.mysql.Manager', }


class Interrogator(object):
    def get_filesystem_volume_stats(self, fs_path):
        out, err = utils.execute_with_timeout(
            "stat",
            "-f",
            "-t",
            fs_path)
        if err:
            LOG.error(err)
            raise RuntimeError("Filesystem not found (%s) : %s"
                               % (fs_path, err))
        stats = out.split()
        output = {}
        output['block_size'] = int(stats[4])
        output['total_blocks'] = int(stats[6])
        output['free_blocks'] = int(stats[7])
        output['total'] = int(stats[6]) * int(stats[4])
        output['free'] = int(stats[7]) * int(stats[4])
        output['used'] = int(output['total']) - int(output['free'])
        return output
