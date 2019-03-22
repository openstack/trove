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

from trove.common import cfg
from trove.common import remote

CONF = cfg.CONF
MGMT_NETWORKS = None


def get_management_networks(context):
    """Cache the management network names.

    When CONF.management_networks is changed, the Trove service needs to
    restart so the global cache will be refreshed.
    """
    global MGMT_NETWORKS

    if MGMT_NETWORKS is not None:
        return MGMT_NETWORKS

    MGMT_NETWORKS = []
    if len(CONF.management_networks) > 0:
        neutron_client = remote.create_neutron_client(context)

        for net_id in CONF.management_networks:
            MGMT_NETWORKS.append(
                neutron_client.show_network(net_id)['network']['name']
            )

    return MGMT_NETWORKS


def reset_management_networks():
    """This method is only for testing purpose."""
    global MGMT_NETWORKS

    MGMT_NETWORKS = None
