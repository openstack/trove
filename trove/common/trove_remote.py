# Copyright 2016 Tesora Inc.
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

from oslo_utils.importutils import import_class

from trove.common import cfg
from trove.common.remote import get_endpoint
from trove.common.remote import normalize_url

from troveclient.v1 import client as TroveClient

CONF = cfg.CONF


"""
NOTE(mwj, Apr 2016):
This module is separated from remote.py because remote.py is used
on the Trove guest, but the trove client is not installed on the guest,
so the imports here would fail.
"""


def trove_client(context, region_name=None):
    if CONF.trove_url:
        url = '%(url)s%(tenant)s' % {
            'url': normalize_url(CONF.trove_url),
            'tenant': context.tenant}
    else:
        url = get_endpoint(context.service_catalog,
                           service_type=CONF.trove_service_type,
                           endpoint_region=region_name or CONF.os_region_name,
                           endpoint_type=CONF.trove_endpoint_type)

    client = TroveClient.Client(context.user, context.auth_token,
                                project_id=context.tenant,
                                auth_url=CONF.trove_auth_url)
    client.client.auth_token = context.auth_token
    client.client.management_url = url
    return client


def create_trove_client(*arg, **kwargs):
    return import_class(CONF.remote_trove_client)(*arg, **kwargs)
