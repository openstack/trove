# Copyright 2010-2012 OpenStack Foundation
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

from trove.common import cfg
from trove.common import exception
from trove.openstack.common.importutils import import_class

from cinderclient.v2 import client as CinderClient
from heatclient.v1 import client as HeatClient
from keystoneclient.service_catalog import ServiceCatalog
from novaclient.v1_1.client import Client
from swiftclient.client import Connection

CONF = cfg.CONF

PROXY_AUTH_URL = CONF.trove_auth_url
USE_SNET = CONF.backup_use_snet


def normalize_url(url):
    """Adds trailing slash if necessary."""
    if not url.endswith('/'):
        return '%(url)s/' % {'url': url}
    else:
        return url


def get_endpoint(service_catalog, service_type=None, endpoint_region=None,
                 endpoint_type='publicURL'):
    """
    Select an endpoint from the service catalog

    We search the full service catalog for services
    matching both type and region. If the client
    supplied no region then any endpoint matching service_type
    is considered a match. There must be one -- and
    only one -- successful match in the catalog,
    otherwise we will raise an exception.

    Some parts copied from glance/common/auth.py.
    """
    if not service_catalog:
        raise exception.EmptyCatalog()

    # per IRC chat, X-Service-Catalog will be a v2 catalog regardless of token
    # format; see https://bugs.launchpad.net/python-keystoneclient/+bug/1302970
    # 'token' key necessary to get past factory validation
    sc = ServiceCatalog.factory({'token': None,
                                 'serviceCatalog': service_catalog})
    urls = sc.get_urls(service_type=service_type, region_name=endpoint_region,
                       endpoint_type=endpoint_type)

    if not urls:
        raise exception.NoServiceEndpoint(service_type=service_type,
                                          endpoint_region=endpoint_region,
                                          endpoint_type=endpoint_type)

    if len(urls) > 1:
        raise exception.RegionAmbiguity(service_type=service_type,
                                        endpoint_region=endpoint_region)

    return urls[0]


def dns_client(context):
    from trove.dns.manager import DnsManager
    return DnsManager()


def guest_client(context, id):
    from trove.guestagent.api import API
    return API(context, id)


def nova_client(context):
    if CONF.nova_compute_url:
        url = '%(nova_url)s%(tenant)s' % {
            'nova_url': normalize_url(CONF.nova_compute_url),
            'tenant': context.tenant}
    else:
        url = get_endpoint(context.service_catalog,
                           service_type=CONF.nova_compute_service_type,
                           endpoint_region=CONF.os_region_name)

    client = Client(context.user, context.auth_token,
                    project_id=context.tenant, auth_url=PROXY_AUTH_URL)
    client.client.auth_token = context.auth_token
    client.client.management_url = url
    return client


def create_admin_nova_client(context):
    """
    Creates client that uses trove admin credentials
    :return: a client for nova for the trove admin
    """
    client = create_nova_client(context)
    client.client.auth_token = None
    return client


def cinder_client(context):
    if CONF.cinder_url:
        url = '%(cinder_url)s%(tenant)s' % {
            'cinder_url': normalize_url(CONF.cinder_url),
            'tenant': context.tenant}
    else:
        url = get_endpoint(context.service_catalog,
                           service_type=CONF.cinder_service_type,
                           endpoint_region=CONF.os_region_name)

    client = CinderClient.Client(context.user, context.auth_token,
                                 project_id=context.tenant,
                                 auth_url=PROXY_AUTH_URL)
    client.client.auth_token = context.auth_token
    client.client.management_url = url
    return client


def heat_client(context):
    if CONF.heat_url:
        url = '%(heat_url)s%(tenant)s' % {
            'heat_url': normalize_url(CONF.heat_url),
            'tenant': context.tenant}
    else:
        url = get_endpoint(context.service_catalog,
                           service_type=CONF.heat_service_type,
                           endpoint_region=CONF.os_region_name)

    client = HeatClient.Client(token=context.auth_token,
                               os_no_client_auth=True,
                               endpoint=url)
    return client


def swift_client(context):
    if CONF.swift_url:
        # swift_url has a different format so doesn't need to be normalized
        url = '%(swift_url)s%(tenant)s' % {'swift_url': CONF.swift_url,
                                           'tenant': context.tenant}
    else:
        url = get_endpoint(context.service_catalog,
                           service_type=CONF.swift_service_type,
                           endpoint_region=CONF.os_region_name)

    client = Connection(preauthurl=url,
                        preauthtoken=context.auth_token,
                        tenant_name=context.tenant,
                        snet=USE_SNET)
    return client


def neutron_client(context):
    from neutronclient.v2_0 import client as NeutronClient
    if CONF.neutron_url:
        # neutron endpoint url / publicURL does not include tenant segment
        url = CONF.neutron_url
    else:
        url = get_endpoint(context.service_catalog,
                           service_type=CONF.neutron_service_type,
                           endpoint_region=CONF.os_region_name)

    client = NeutronClient.Client(token=context.auth_token,
                                  endpoint_url=url)
    return client


create_dns_client = import_class(CONF.remote_dns_client)
create_guest_client = import_class(CONF.remote_guest_client)
create_nova_client = import_class(CONF.remote_nova_client)
create_swift_client = import_class(CONF.remote_swift_client)
create_cinder_client = import_class(CONF.remote_cinder_client)
create_heat_client = import_class(CONF.remote_heat_client)
create_neutron_client = import_class(CONF.remote_neutron_client)
