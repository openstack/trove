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

import abc
import six

from trove.common import cfg


CONF = cfg.CONF


@six.add_metaclass(abc.ABCMeta)
class ModuleDriver(object):
    """Base class that defines the contract for module drivers.

    Note that you don't have to derive from this class to have a valid
    driver; it is purely a convenience.
    """

    def get_type(self):
        """This is used when setting up a module in Trove, and is here for
        code clarity.  It just returns the name of the driver.
        """
        return self.get_name()

    def get_name(self):
        """Attempt to generate a usable name based on the class name. If
        overridden, must be in lower-case.
        """
        return self.__class__.__name__.lower().replace(
            'driver', '').replace(' ', '_')

    @abc.abstractmethod
    def get_description(self):
        """Description for the driver."""
        pass

    @abc.abstractmethod
    def get_updated(self):
        """Date the driver was last updated."""
        pass

    @abc.abstractmethod
    def apply(self, name, datastore, ds_version, data_file):
        """Apply the data to the guest instance. Return status and message
        as a tupple.
        """
        return False, "Not a concrete driver"

    @abc.abstractmethod
    def remove(self, name, datastore, ds_version, data_file):
        """Remove the data from the guest instance.  Return status and message
        as a tupple.
        """
        return False, "Not a concrete driver"
