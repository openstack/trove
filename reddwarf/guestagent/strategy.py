# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
from reddwarf.common import utils
from reddwarf.openstack.common import log as logging


LOG = logging.getLogger(__name__)


class Strategy(object):
    __metaclass__ = abc.ABCMeta

    __strategy_ns__ = None

    __strategy_name__ = None
    __strategy_type__ = None

    def __init__(self):
        self.name = self.get_canonical_name()
        LOG.debug("Loaded strategy %s", self.name)

    def is_enabled(self):
        """
        Is this Strategy enabled?

        :retval: Boolean
        """
        return True

    @classmethod
    def get_strategy(cls, name, ns=None):
        """
        Load a strategy from namespace
        """
        ns = ns or cls.__strategy_ns__
        if ns is None:
            raise RuntimeError(
                'No namespace provided or __strategy_ns__ unset')

        LOG.debug('Looking for strategy %s in %s', name, ns)

        return utils.import_class(ns + "." + name)

    @classmethod
    def get_canonical_name(cls):
        """
        Return the strategy name
        """
        type_ = cls.get_strategy_type()
        name = cls.get_strategy_name()
        return "%s:%s" % (type_, name)

    @classmethod
    def get_strategy_name(cls):
        return cls.__strategy_name__

    @classmethod
    def get_strategy_type(cls):
        return cls.__strategy_type__
