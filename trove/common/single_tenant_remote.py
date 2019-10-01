# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cinderclient.v2 import client as CinderClient
from keystoneauth1 import loading
from keystoneauth1 import session
from neutronclient.v2_0 import client as NeutronClient
from novaclient.client import Client as NovaClient
import swiftclient

from trove.common import cfg
from trove.common.remote import normalize_url

CONF = cfg.CONF
_SESSION = None


def get_keystone_session():
    global _SESSION

    if not _SESSION:
        loader = loading.get_plugin_loader('password')
        auth = loader.load_from_options(
            username=CONF.nova_proxy_admin_user,
            password=CONF.nova_proxy_admin_pass,
            project_name=CONF.nova_proxy_admin_tenant_name,
            user_domain_name=CONF.nova_proxy_admin_user_domain_name,
            project_domain_name=CONF.nova_proxy_admin_project_domain_name,
            auth_url=CONF.trove_auth_url)
        _SESSION = session.Session(auth=auth)

    return _SESSION


def nova_client_trove_admin(context, region_name=None, password=None):
    """
    Returns a nova client object with the trove admin credentials
    :param context: original context from user request
    :type context: trove.common.context.TroveContext
    :return novaclient: novaclient with trove admin credentials
    :rtype: novaclient.client.Client
    """

    ks_session = get_keystone_session()
    client = NovaClient(
        CONF.nova_client_version,
        session=ks_session,
        service_type=CONF.nova_compute_service_type,
        region_name=region_name or CONF.os_region_name,
        insecure=CONF.nova_api_insecure,
        endpoint_type=CONF.nova_compute_endpoint_type)

    if CONF.nova_compute_url and CONF.nova_proxy_admin_tenant_id:
        client.client.endpoint_override = "%s/%s/" % (
            normalize_url(CONF.nova_compute_url),
            CONF.nova_proxy_admin_tenant_id)

    return client


def cinder_client_trove_admin(context, region_name=None):
    """
    Returns a cinder client object with the trove admin credentials
    :param context: original context from user request
    :type context: trove.common.context.TroveContext
    :return cinderclient: cinderclient with trove admin credentials
    """
    ks_session = get_keystone_session()
    client = CinderClient.Client(
        session=ks_session,
        service_type=CONF.cinder_service_type,
        region_name=region_name or CONF.os_region_name,
        insecure=CONF.cinder_api_insecure,
        endpoint_type=CONF.cinder_endpoint_type)

    if CONF.cinder_url and CONF.nova_proxy_admin_tenant_id:
        client.client.management_url = "%s/%s/" % (
            normalize_url(CONF.cinder_url), CONF.nova_proxy_admin_tenant_id)

    return client


def neutron_client_trove_admin(context, region_name=None):
    """
    Returns a neutron client object with the trove admin credentials
    :param context: original context from user request
    :type context: trove.common.context.TroveContext
    :return neutronclient: neutronclient with trove admin credentials
    """
    ks_session = get_keystone_session()
    client = NeutronClient.Client(
        session=ks_session,
        service_type=CONF.neutron_service_type,
        region_name=region_name or CONF.os_region_name,
        insecure=CONF.neutron_api_insecure,
        endpoint_type=CONF.neutron_endpoint_type)

    if CONF.neutron_url:
        client.management_url = CONF.neutron_url

    return client


def swift_client_trove_admin(context, region_name=None):
    ks_session = get_keystone_session()
    client = swiftclient.Connection(
        session=ks_session,
        insecure=CONF.swift_api_insecure,
        os_options={
            'region_name': region_name or CONF.os_region_name,
            'service_type': CONF.swift_service_type,
            'endpoint_type': CONF.swift_endpoint_type
        }
    )

    return client
