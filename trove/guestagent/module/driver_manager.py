# Copyright 2016 Tesora, Inc.
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

from oslo_log import log as logging
from oslo_utils import encodeutils
import stevedore

from trove.common import base_exception as exception
from trove.common import cfg
from trove.common.i18n import _

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ModuleDriverManager(object):

    MODULE_DRIVER_NAMESPACE = 'trove.guestagent.module.drivers'

    def __init__(self):
        LOG.info('Initializing module driver manager.')

        self._drivers = {}
        self._module_types = [mt.lower() for mt in CONF.module_types]

        self._load_drivers()

    def _load_drivers(self):
        manager = stevedore.enabled.EnabledExtensionManager(
            namespace=self.MODULE_DRIVER_NAMESPACE,
            check_func=self._check_extension,
            invoke_on_load=True,
            invoke_kwds={})
        try:
            manager.map(self.add_driver_extension)
        except stevedore.exception.NoMatches:
            LOG.info("No module drivers loaded")

    def _check_extension(self, extension):
        """Checks for required methods in driver objects."""
        driver = extension.obj
        supported = False
        try:
            LOG.info('Loading Module driver: %s', driver.get_type())
            if driver.get_type() != driver.get_type().lower():
                raise AttributeError(_("Driver 'type' must be lower-case"))
            LOG.debug('  description: %s', driver.get_description())
            LOG.debug('  updated    : %s', driver.get_updated())
            required_attrs = ['apply', 'remove']
            for attr in required_attrs:
                if not hasattr(driver, attr):
                    raise AttributeError(
                        _("Driver '%(type)s' missing attribute: %(attr)s")
                        % {'type': driver.get_type(), 'attr': attr})
            if driver.get_type() in self._module_types:
                supported = True
            else:
                LOG.info("Driver '%s' not supported, skipping",
                         driver.get_type())
        except AttributeError as ex:
            LOG.exception("Exception loading module driver: %s",
                          encodeutils.exception_to_unicode(ex))

        return supported

    def add_driver_extension(self, extension):
        # Add a module driver from the extension.
        # If the stevedore manager is changed to one that doesn't
        # check the extension driver, then it should be done manually here
        # by calling self._check_extension(extension)
        driver = extension.obj
        driver_type = driver.get_type()
        LOG.info('Loaded module driver: %s', driver_type)

        if driver_type in self._drivers:
            raise exception.Error(_("Found duplicate driver: %s") %
                                  driver_type)
        self._drivers[driver_type] = driver

    def get_driver(self, driver_type):
        found = None
        if driver_type in self._drivers:
            found = self._drivers[driver_type]
        return found
