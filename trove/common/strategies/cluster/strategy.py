# Copyright 2014 eBay Software Foundation
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

from oslo_config.cfg import NoSuchOptError

from trove.common import cfg
from trove.common.utils import import_class
from trove.openstack.common import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def load_api_strategy(manager):
    clazz = CONF.get(manager).get('api_strategy')
    LOG.debug("Loading class %s" % clazz)
    api_strategy = import_class(clazz)
    return api_strategy()


def load_taskmanager_strategy(manager):
    try:
        clazz = CONF.get(manager).get('taskmanager_strategy')
        LOG.debug("Loading class %s" % clazz)
        taskmanager_strategy = import_class(clazz)
        return taskmanager_strategy()
    except NoSuchOptError:
        return None


def load_guestagent_strategy(manager):
    try:
        clazz = CONF.get(manager).get('guestagent_strategy')
        LOG.debug("Loading class %s" % clazz)
        guestagent_strategy = import_class(clazz)
        return guestagent_strategy()
    except NoSuchOptError:
        return None
