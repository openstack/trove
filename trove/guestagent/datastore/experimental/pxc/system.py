# Copyright [2015] Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from trove.guestagent.common import operating_system


def service_discovery(service_candidates):
    result = operating_system.service_discovery(service_candidates)
    if result['type'] == 'sysvinit':
        result['cmd_bootstrap_pxc_cluster'] = ("sudo service %s bootstrap-pxc"
                                               % result['service'])
    elif result['type'] == 'systemd':
        result['cmd_bootstrap_pxc_cluster'] = ("sudo systemctl start "
                                               "%s@bootstrap.service"
                                               % result['service'])
    return result
