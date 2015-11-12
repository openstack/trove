#  Copyright 2013 Mirantis Inc.
#  All Rights Reserved.
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

from trove.common import cfg

CONF = cfg.CONF

SERVICE_CANDIDATES = ["cassandra"]

CASSANDRA_DATA_DIR = "/var/lib/cassandra/data"
CASSANDRA_CONF = "/etc/cassandra/cassandra.yaml"
CASSANDRA_TEMP_CONF = "/tmp/cassandra.yaml"
CASSANDRA_TEMP_DIR = "/tmp/cassandra"

CASSANDRA_STATUS = """echo "use system;" > /tmp/check; cqlsh -f /tmp/check"""

CASSANDRA_KILL = "sudo killall java  || true"
SERVICE_STOP_TIMEOUT = 60
INSTALL_TIMEOUT = 10000
