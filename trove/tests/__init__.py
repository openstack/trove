# Copyright 2019 Catalyst Cloud Ltd.
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

import os

# Groups
DBAAS_API = "dbaas.api"
DBAAS_API_INSTANCES = "dbaas.api.instances"
DBAAS_API_INSTANCES_DELETE = "dbaas.api.instances.delete"
DBAAS_API_USERS = "dbaas.api.users"
DBAAS_API_USERS_ACCESS = "dbaas.api.users.access"
DBAAS_API_USERS_ROOT = "dbaas.api.users.root"
DBAAS_API_DATABASES = "dbaas.api.databases"
DBAAS_API_VERSIONS = "dbaas.api.versions"
DBAAS_API_DATASTORES = "dbaas.api.datastores"
DBAAS_API_MGMT_DATASTORES = "dbaas.api.mgmt.datastores"
DBAAS_API_INSTANCE_ACTIONS = "dbaas.api.instances.actions"
DBAAS_API_BACKUPS = "dbaas.api.backups"
DBAAS_API_CONFIGURATIONS = "dbaas.api.configurations"
DBAAS_API_REPLICATION = "dbaas.api.replication"

# Use '-t' to avoid the warning message 'mesg: ttyname failed: Inappropriate
# ioctl for device'
SSH_CMD = ("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "
           "-o LogLevel=quiet -t -i %s" %
           os.environ.get("TROVE_TEST_SSH_KEY_FILE", ""))
