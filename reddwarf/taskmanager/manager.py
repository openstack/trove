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
import traceback
import weakref

from eventlet import greenthread

from reddwarf.common import exception
from reddwarf.common import service
from reddwarf.taskmanager import models
from reddwarf.taskmanager.models import BuiltInstanceTasks
from reddwarf.taskmanager.models import FreshInstanceTasks


LOG = logging.getLogger(__name__)


class TaskManager(service.Manager):
    """Task manager impl"""

    def __init__(self, *args, **kwargs):
        self.tasks = weakref.WeakKeyDictionary()
        super(TaskManager, self).__init__(*args, **kwargs)
        LOG.info(_("TaskManager init %s %s") % (args, kwargs))

    def periodic_tasks(self, raise_on_error=False):
        LOG.debug("No. of running tasks: %r" % len(self.tasks))

    def _wrapper(self, method, context, *args, **kwargs):
        """Maps the respective manager method with a task counter."""
        # TODO(rnirmal): Just adding a basic counter. Will revist and
        # re-implement when we have actual tasks.
        self.tasks[greenthread.getcurrent()] = context
        try:
            func = getattr(self, method)
            func(context, *args, **kwargs)
        except Exception as e:
            LOG.error("Got an error running %s!" % method)
            LOG.error(traceback.format_exc())
        finally:
            del self.tasks[greenthread.getcurrent()]

    def resize_volume(self, context, instance_id, new_size):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.resize_volume(new_size)

    def resize_flavor(self, context, instance_id, new_flavor_id,
                      old_memory_size, new_memory_size):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.resize_flavor(new_flavor_id, old_memory_size,
                                     new_memory_size)

    def restart(self, context, instance_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.restart()

    def delete_instance(self, context, instance_id):
        try:
            instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
            instance_tasks.delete_async()
        except exception.UnprocessableEntity as upe:
            instance_tasks = models.FreshInstanceTasks.load(context, instance_id)
            instance_tasks.delete_async()

    def create_instance(self, context, instance_id, name, flavor_id,
                        flavor_ram, image_id, databases, users, service_type,
                        volume_size):
        instance_tasks = FreshInstanceTasks.load(context, instance_id)
        instance_tasks.create_instance(flavor_id, flavor_ram, image_id,
                                       databases, users, service_type,
                                       volume_size)
