# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack LLC.
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

from reddwarf.common import config
from novaclient.v1_1.client import Client



CONFIG = config.Config


def create_guest_client(context, id):
    from reddwarf.guestagent.api import API
    return API(context, id)


def create_nova_client(context):
    # Quite annoying but due to a paste config loading bug.
    # TODO(hub-cap): talk to the openstack-common people about this
    PROXY_ADMIN_USER = CONFIG.get('reddwarf_proxy_admin_user', 'admin')
    PROXY_ADMIN_PASS = CONFIG.get('reddwarf_proxy_admin_pass',
                                  '3de4922d8b6ac5a1aad9')
    PROXY_ADMIN_TENANT_NAME = CONFIG.get(
                                    'reddwarf_proxy_admin_tenant_name',
                                    'admin')
    PROXY_AUTH_URL = CONFIG.get('reddwarf_auth_url',
                                'http://0.0.0.0:5000/v2.0')
    REGION_NAME = CONFIG.get('nova_region_name', 'RegionOne')
    SERVICE_TYPE = CONFIG.get('nova_service_type', 'compute')
    SERVICE_NAME = CONFIG.get('nova_service_name', 'Compute Service')

    #TODO(cp16net) need to fix this proxy_tenant_id
    client = Client(PROXY_ADMIN_USER, PROXY_ADMIN_PASS,
        PROXY_ADMIN_TENANT_NAME, PROXY_AUTH_URL,
        proxy_tenant_id=context.tenant,
        proxy_token=context.auth_tok,
        region_name=REGION_NAME,
        service_type=SERVICE_TYPE,
        service_name=SERVICE_NAME)
    client.authenticate()
    return client


if CONFIG.get("remote_implementation", "real") == "fake":
    # Override the functions above with fakes.

    from reddwarf.tests.fakes.nova import fake_create_nova_client
    from reddwarf.tests.fakes.guestagent import fake_create_guest_client

    def create_guest_client(context, id):
        return fake_create_guest_client(context, id)

    def create_nova_client(context):
        return fake_create_nova_client(context)
