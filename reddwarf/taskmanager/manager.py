# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import logging

LOG = logging.getLogger(__name__)


class TaskManager(object):
    """Task manager impl"""

    def __init__(self, *args, **kwargs):
        LOG.info("TaskManager init %s %s" % (args, kwargs))

    def periodic_tasks(self, raise_on_error=False):
        LOG.info("Launching a periodic task")

    def test_method(self, context):
        LOG.info("test_method called with context %s" % context)
