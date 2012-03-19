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

"""


import functools
import logging

from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.common import service


LOG = logging.getLogger(__name__)


class GuestManager(service.Manager):

    """Manages the tasks within a Guest VM."""

    def __init__(self, guest_drivers=None, *args, **kwargs):
        if not guest_drivers:
            #TODO(hub-cap): fix this, maybe make it a flag
            guest_drivers = ['reddwarf.guestagent.dbaas.DBaaSAgent',
                             'reddwarf.guestagent.pkg.PkgAgent']
        classes = []
        for guest_driver in guest_drivers:
            LOG.info(guest_driver)
            driver = utils.import_class(guest_driver)
            classes.append(driver)
        try:
            cls = type("GuestDriver", tuple(set(classes)), {})
            self.driver = cls()
        except TypeError as te:
            msg = "An issue occurred instantiating the GuestDriver as the " \
                  "following classes: " + str(classes) + \
                  " Exception=" + str(te)
            raise TypeError(msg)
        super(GuestManager, self).__init__(*args, **kwargs)

    def init_host(self):
        """Method for any service initialization"""
        pass

    def periodic_tasks(self, raise_on_error=False):
        """Method for running any periodic tasks.

           Right now does the status updates"""
        status_method = "update_status"
        try:
            getattr(self.driver, status_method)()
        except AttributeError as ae:
            LOG.error("Method %s not found for driver %s", status_method,
                      self.driver)
            if raise_on_error:
                raise ae

    def upgrade(self, context):
        """Upgrade the guest agent and restart the agent"""
        LOG.debug(_("Self upgrade of guest agent issued"))

    def __getattr__(self, key):
        """Converts all method calls and direct it at the driver"""
        return functools.partial(self._mapper, key)

    def _mapper(self, method, context, *args, **kwargs):
        """ Tries to call the respective driver method """
        try:
            return getattr(self.driver, method)(*args, **kwargs)
        except AttributeError:
            LOG.error("Method %s not found for driver %s", method, self.driver)
            raise exception.NotFound("Method not available for the "
                                     "chosen driver")
