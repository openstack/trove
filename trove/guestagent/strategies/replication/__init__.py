# Copyright 2014 Tesora, Inc.
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

from trove.common import cfg
from trove.common.strategies.strategy import Strategy


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


__replication_instance = None
__replication_manager = None
__replication_namespace = None
__replication_strategy = None


def get_instance(manager):
    global __replication_instance
    global __replication_manager
    global __replication_namespace
    if not __replication_instance or manager != __replication_manager:
        replication_strategy = get_strategy(manager)
        __replication_namespace = CONF.get(manager).replication_namespace
        replication_strategy_cls = get_strategy_cls(
            replication_strategy, __replication_namespace)
        __replication_instance = replication_strategy_cls()
        __replication_manager = manager
    LOG.debug('Got replication instance from: %(namespace)s.%(strategy)s',
              {'namespace': __replication_namespace,
               'strategy': __replication_strategy})
    return __replication_instance


def get_strategy(manager):
    global __replication_strategy
    if not __replication_strategy or manager != __replication_manager:
        __replication_strategy = CONF.get(manager).replication_strategy
    return __replication_strategy


def get_strategy_cls(replication_driver, ns=__name__):
    return Strategy.get_strategy(replication_driver, ns)
