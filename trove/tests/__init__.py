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

DBAAS_API = "dbaas.api"
PRE_INSTANCES = "dbaas.api.pre_instances"
INSTANCES = "dbaas.api.instances"
POST_INSTANCES = "dbaas.api.post_instances"

# Use '-t' to avoid the warning message 'mesg: ttyname failed: Inappropriate
# ioctl for device'
SSH_CMD = ("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "
           "-o LogLevel=quiet -t -i %s" %
           os.environ.get("TROVE_TEST_SSH_KEY_FILE", ""))
