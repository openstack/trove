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
import netaddr
from oslo_cache import core
from oslo_log import log as logging
from neutronclient.common import exceptions as neutron_exceptions

from trove.common import cache
from trove.common import cfg
from trove.common import clients
from trove.common import exception

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
MGMT_NETWORKS = None
MGMT_CIDRS = None
NEUTRON_EXTENSION_CACHE = {}
PROJECT_ID_EXT_ALIAS = 'project-id'

MEMOIZE_PORTS = core.get_memoization_decorator(
    conf=CONF,
    region=cache.get_cache_region(),
    group="instance_ports_cache")


def check_extension_enabled(client, extension_alias):
    """Check if an extension is enabled in Neutron."""
    global NEUTRON_EXTENSION_CACHE

    if extension_alias in NEUTRON_EXTENSION_CACHE:
        status = NEUTRON_EXTENSION_CACHE[extension_alias]
        LOG.debug(f"Neutron extension {extension_alias} cached as "
                  f"{'enabled' if status else 'disabled'}")
    else:
        try:
            client.show_extension(extension_alias)
            LOG.debug(f'Neutron extension {extension_alias} found enabled')
            NEUTRON_EXTENSION_CACHE[extension_alias] = True
        except neutron_exceptions.NotFound:
            LOG.debug(f'Neutron extension {extension_alias} is not enabled')
            NEUTRON_EXTENSION_CACHE[extension_alias] = False

    return NEUTRON_EXTENSION_CACHE[extension_alias]


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
        neutron_client = clients.create_neutron_client(context)

        for net_id in CONF.management_networks:
            MGMT_NETWORKS.append(
                neutron_client.show_network(net_id)['network']['name']
            )

    return MGMT_NETWORKS


def reset_management_networks():
    """This method is only for testing purpose."""
    global MGMT_NETWORKS

    MGMT_NETWORKS = None


def check_subnet_router(client, subnet_id):
    """Check if the subnet is associated with a router."""
    router_ports = client.list_ports(
        device_owner="network:router_interface",
        fixed_ips=f"subnet_id={subnet_id}"
    )["ports"] + client.list_ports(
        device_owner="network:router_interface_distributed",
        fixed_ips=f"subnet_id={subnet_id}"
    )["ports"] + client.list_ports(
        device_owner="network:ha_router_replicated_interface",
        fixed_ips=f"subnet_id={subnet_id}")["ports"]
    if not router_ports:
        raise exception.TroveError(f"Subnet {subnet_id} is not "
                                   f"associated with router.")


@MEMOIZE_PORTS
def get_instance_ports(client, instance_id):
    """Get ports attached to the trove instance.

    After the trove instance is created, the attached ports are not changed.
    """
    LOG.info(f'Getting ports for instance {instance_id}')
    return client.list_ports(device_id=instance_id)['ports']


def get_port_fips(client, port_id):
    return client.list_floatingips(port_id=port_id)['floatingips']


def create_port(client, name, description, network_id, security_groups,
                is_public=False, subnet_id=None, ip=None, is_mgmt=False,
                project_id=None):
    enable_access_check = (not is_mgmt and
                           (CONF.network.enable_access_check or is_public))

    port_body = {
        "port": {
            "name": name,
            "description": description,
            "network_id": network_id,
            "security_groups": security_groups
        }
    }

    if subnet_id:
        if enable_access_check:
            check_subnet_router(client, subnet_id)

        fixed_ips = {
            "fixed_ips": [{"subnet_id": subnet_id}]
        }
        if ip:
            fixed_ips['fixed_ips'][0].update({'ip_address': ip})
        port_body['port'].update(fixed_ips)

    port = client.create_port(body=port_body)
    port_id = port['port']['id']

    if not subnet_id and enable_access_check:
        # Check if the subnet has been associated with a router.
        subnet_id = port['port']['fixed_ips'][0]['subnet_id']
        check_subnet_router(client, subnet_id)

    if is_public:
        make_port_public(client, port_id, project_id)

    return port_id


def delete_port(client, id):
    ret = client.list_floatingips(port_id=id)
    if len(ret['floatingips']) > 0:
        for fip in ret['floatingips']:
            try:
                client.delete_floatingip(fip['id'])
            except Exception as e:
                LOG.error(
                    'Failed to delete floating IP for port %s, error: %s',
                    id, str(e)
                )

    client.delete_port(id)


def make_port_public(client, port_id, project_id):
    """Associate floating IP with the port."""
    public_network_id = get_public_network(client)
    if not public_network_id:
        raise exception.PublicNetworkNotFound()

    fip_body = {
        "floatingip": {
            'floating_network_id': public_network_id,
            'port_id': port_id,
        }
    }
    if project_id:
        if check_extension_enabled(client, PROJECT_ID_EXT_ALIAS):
            project_id_key = 'project_id'
        else:
            project_id_key = 'tenant_id'
        fip_body['floatingip'][project_id_key] = project_id

    try:
        LOG.debug(f"Creating floating IP for the port {port_id}, "
                  f"request body: {fip_body}")
        ret = client.create_floatingip(fip_body)
        LOG.info(f"Successfully created floating IP "
                 f"{ret['floatingip']['floating_ip_address']} for port "
                 f"{port_id}")
    except Exception as e:
        LOG.error(f"Failed to create public IP with port {port_id}: "
                  f"{str(e)}")
        raise exception.TroveError('Failed to expose instance port to public.')


def get_public_network(client):
    """Get public network ID.

    If not given in the config file, try to query all the public networks and
    use the first one in the list.
    """
    if CONF.network.public_network_id:
        return CONF.network.public_network_id

    kwargs = {'router:external': True}
    ret = client.list_networks(**kwargs)

    if len(ret.get('networks', [])) == 0:
        return None

    return ret['networks'][0].get('id')


def ensure_port_access(client, port_id, is_public, project_id):
    fips = client.list_floatingips(port_id=port_id)["floatingips"]

    if is_public and not fips:
        # Associate floating IP
        LOG.debug(f"Associate public IP with port {port_id}")
        make_port_public(client, port_id, project_id)
        return

    if not is_public and fips:
        # Disassociate floating IP
        for fip in fips:
            LOG.debug(f"Disassociate public IP {fip['floating_ip_address']} "
                      f"from port {port_id}")
            client.delete_floatingip(fip["id"])
        return


def create_security_group(client, name, instance_id):
    body = {
        'security_group': {
            'name': name,
            'description': 'Security group for trove instance %s' % instance_id
        }
    }
    ret = client.create_security_group(body=body)
    return ret['security_group']['id']


def create_security_group_rule(client, sg_id, protocol, ports, remote_ips):
    for remote_ip in remote_ips:
        ip = netaddr.IPNetwork(remote_ip)
        ethertype = 'IPv4' if ip.version == 4 else 'IPv6'

        for port_or_range in set(ports):
            from_, to_ = port_or_range[0], port_or_range[-1]

            body = {
                "security_group_rule": {
                    "direction": "ingress",
                    "ethertype": ethertype,
                    "protocol": protocol,
                    "security_group_id": sg_id,
                    "port_range_min": int(from_),
                    "port_range_max": int(to_),
                    "remote_ip_prefix": remote_ip
                }
            }

            client.create_security_group_rule(body)


def clear_ingress_security_group_rules(client, sg_id):
    rules = client.list_security_group_rules(
        security_group_id=sg_id)['security_group_rules']

    for rule in rules:
        if rule['direction'] == 'ingress':
            client.delete_security_group_rule(rule['id'])


def get_subnet_cidrs(client, network_id=None, subnet_id=None):
    cidrs = []

    # Check subnet first.
    if subnet_id:
        cidrs.append(client.show_subnet(subnet_id)['subnet']['cidr'])
    elif network_id:
        subnets = client.list_subnets(network_id=network_id)['subnets']
        for subnet in subnets:
            cidrs.append(subnet.get('cidr'))

    return cidrs


def get_mamangement_subnet_cidrs(client):
    """Cache the management subnet CIDRS."""
    global MGMT_CIDRS

    if MGMT_CIDRS is not None:
        return MGMT_CIDRS

    MGMT_CIDRS = []
    if len(CONF.management_networks) > 0:
        MGMT_CIDRS = get_subnet_cidrs(client, CONF.management_networks[0])

    return MGMT_CIDRS
