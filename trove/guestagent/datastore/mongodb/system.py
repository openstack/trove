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
CONFIG_CANDIDATES = ["/etc/mongodb.conf", "/etc/mongod.conf"]
MONGOS_UPSTART = "/etc/init/mongos.conf"
TMP_MONGOS_UPSTART = "/tmp/mongos.conf.tmp"
MONGOS_SERVICE_CANDIDATES = ["mongos"]
MONGOD_SERVICE_CANDIDATES = ["mongodb", "mongod"]
MONGODB_KILL = "sudo kill %s"
FIND_PID = "ps xau | grep 'mongo[ds]'"
TIME_OUT = 1000

INIT_EXEC_MONGOS = ("start-stop-daemon --start --quiet --chuid mongodb "
                    "--exec  /usr/bin/mongos -- "
                    "--config {config_file_placeholder}")

MONGOS_UPSTART_CONTENTS = """limit fsize unlimited unlimited  # (file size)
limit cpu unlimited unlimited    # (cpu time)
limit as unlimited unlimited     # (virtual memory size)
limit nofile 64000 64000         # (open files)
limit nproc 64000 64000          # (processes/threads)

pre-start script
    mkdir -p /var/log/mongodb/
end script

start on runlevel [2345]
stop on runlevel [06]

script
  ENABLE_MONGOS="yes"
  if [ -f /etc/default/mongos ]; then . /etc/default/mongos; fi
  if [ "x$ENABLE_MONGOS" = "xyes" ]; then exec %s; fi
end script """ % INIT_EXEC_MONGOS

PACKAGER = pkg.Package()
