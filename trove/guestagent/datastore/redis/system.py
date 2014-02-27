# Copyright (c) 2013 Rackspace
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
Determines operating system version and os depended commands.
"""
from trove.guestagent.common.operating_system import get_os

OS = get_os()
REDIS_CONFIG = '/etc/redis/redis.conf'
REDIS_CONF_DIR = '/etc/redis'
REDIS_INIT = '/etc/init/redis-server.conf'
REDIS_CLI = '/usr/bin/redis-cli'
REDIS_BIN = '/usr/bin/redis-server'
REDIS_CMD_ENABLE = 'update-rc.d redis-server enable'
REDIS_CMD_DISABLE = 'update-rc.d redis-server disable'
REDIS_CMD_START = 'service redis-server start || /bin/true'
REDIS_CMD_STOP = 'service redis-server stop || /bin/true'
REDIS_PACKAGE = 'redis-server'

if OS is 'redhat':
    REDIS_BIN = '/usr/libexec/redis-server'
    REDIS_CMD_ENABLE = 'chkconfig redis-server on'
    REDIS_CMD_DISABLE = 'chkconfig redis-server off'
    REDIS_CMD_START = 'service redis-server start'
    REDIS_CMD_STOP = 'service redis-server stop'
