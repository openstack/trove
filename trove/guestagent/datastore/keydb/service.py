# Copyright 2026 PS Cloud Services
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from trove.guestagent.datastore.redis_common import service


class KeyDBApp(service.RedisApp):
    DATASTORE_NAME = 'keydb'
    CLI_BINARY = 'keydb-cli'
    CONFIG_FILE = "/etc/keydb/keydb.conf"
    CNF_INCLUDE_DIR = '/etc/keydb/conf.d'
    SOCKET_PATH = '/var/lib/keydb-socket'
    CONTAINER_SOCKET = '/var/run/keydb/keydb.sock'
    ACL_FILE = '/var/lib/keydb/conf.d/users.acl'
    SERVER_BINARY = 'keydb-server'
    DATA_ENV_NAME = 'KEYDB_DATA'

    HEALTHCHECK = {
        "test": [
            "CMD-SHELL",
            f"keydb-cli -s {CONTAINER_SOCKET} ping | grep -qx PONG"],
        "start_period": 10 * 1000000000,  # 10 seconds in nanoseconds
        "interval": 10 * 1000000000,
        "timeout": 5 * 1000000000,
        "retries": 3
    }
