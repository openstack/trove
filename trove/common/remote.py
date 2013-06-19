# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from trove.common import cfg
from trove.openstack.common.importutils import import_class
from novaclient.v1_1.client import Client
from swiftclient.client import Connection

CONF = cfg.CONF

COMPUTE_URL = CONF.nova_compute_url
PROXY_AUTH_URL = CONF.trove_auth_url
VOLUME_URL = CONF.nova_volume_url
OBJECT_STORE_URL = CONF.swift_url
USE_SNET = CONF.backup_use_snet


def dns_client(context):
    from trove.dns.manager import DnsManager
    return DnsManager()


def guest_client(context, id):
    from trove.guestagent.api import API
    return API(context, id)


def nova_client(context):
    client = Client(context.user, context.auth_token,
                    project_id=context.tenant, auth_url=PROXY_AUTH_URL)
    client.client.auth_token = context.auth_token
    client.client.management_url = "%s/%s/" % (COMPUTE_URL, context.tenant)

    return client


def create_admin_nova_client(context):
    """
    Creates client that uses trove admin credentials
    :return: a client for nova for the trove admin
    """
    client = create_nova_client(context)
    client.client.auth_token = None
    return client


def nova_volume_client(context):
    # Quite annoying but due to a paste config loading bug.
    # TODO(hub-cap): talk to the openstack-common people about this
    client = Client(context.user, context.auth_token,
                    project_id=context.tenant, auth_url=PROXY_AUTH_URL)
    client.client.auth_token = context.auth_token
    client.client.management_url = "%s/%s/" % (VOLUME_URL, context.tenant)

    return client


def swift_client(context):
    client = Connection(preauthurl=OBJECT_STORE_URL + context.tenant,
                        preauthtoken=context.auth_token,
                        tenant_name=context.tenant,
                        snet=USE_SNET)
    return client


create_dns_client = import_class(CONF.remote_dns_client)
create_guest_client = import_class(CONF.remote_guest_client)
create_nova_client = import_class(CONF.remote_nova_client)
create_nova_volume_client = import_class(CONF.remote_nova_volume_client)
create_swift_client = import_class(CONF.remote_swift_client)
