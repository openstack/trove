# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack Foundation
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
import os.path
from trove.common import cfg

CONF = cfg.CONF

REDHAT = 'redhat'
DEBIAN = 'debian'

# The default is debian
OS = DEBIAN
MYSQL_CONFIG = "/etc/mysql/my.cnf"
MYSQL_BIN = "/usr/sbin/mysqld"
MYSQL_CMD_ENABLE = "sudo update-rc.d mysql enable"
MYSQL_CMD_DISABLE = "sudo update-rc.d mysql disable"
MYSQL_CMD_START = "sudo service mysql start || /bin/true"
MYSQL_CMD_STOP = "sudo service mysql stop || /bin/true"

if os.path.isfile("/etc/redhat-release"):
    OS = REDHAT
    MYSQL_CONFIG = "/etc/my.cnf"
    if CONF.service_type == 'percona':
        MYSQL_CMD_ENABLE = "sudo chkconfig mysql on"
        MYSQL_CMD_DISABLE = "sudo chkconfig mysql off"
        MYSQL_CMD_START = "sudo service mysql start"
        MYSQL_CMD_STOP = "sudo service mysql stop"
    else:
        MYSQL_BIN = "/usr/libexec/mysqld"
        MYSQL_CMD_ENABLE = "sudo chkconfig mysqld on"
        MYSQL_CMD_DISABLE = "sudo chkconfig mysqld off"
        MYSQL_CMD_START = "sudo service mysqld start"
        MYSQL_CMD_STOP = "sudo service mysqld stop"
