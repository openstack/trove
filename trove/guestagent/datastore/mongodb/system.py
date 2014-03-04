#   Copyright (c) 2014 Mirantis, Inc.
#   All Rights Reserved.
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

from trove.guestagent import pkg

MONGODB_MOUNT_POINT = "/var/lib/mongodb"
# After changing bind address mongodb accepts connection
# on real IP, not on the localhost
CMD_STATUS = "mongostat --host %s -n 1 | grep connected"

TMP_CONFIG = "/tmp/mongodb.conf.tmp"
CONFIG = "/etc/mongodb.conf"
SERVICE_CANDIDATES = ["mongodb", "mongod"]
MONGODB_KILL = "sudo kill %s"
FIND_PID = "ps xau | grep mongod"
TIME_OUT = 1000

PACKAGER = pkg.Package()
