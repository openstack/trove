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

from keystoneauth1.identity import v3
from keystoneauth1 import session as ka_session

from oslo_utils.importutils import import_class

from trove.common import cfg
from trove.common.remote import get_endpoint
from trove.common.remote import normalize_url

from glanceclient import Client

CONF = cfg.CONF


def glance_client(context, region_name=None):

    # We should allow glance to get the endpoint from the service
    # catalog, but to do so we would need to be able to specify
    # the endpoint_filter on the API calls, but glance
    # doesn't currently allow that.  As a result, we must
    # specify the endpoint explicitly.
    if CONF.glance_url:
        endpoint_url = '%(url)s%(tenant)s' % {
            'url': normalize_url(CONF.glance_url),
            'tenant': context.tenant}
    else:
        endpoint_url = get_endpoint(
            context.service_catalog, service_type=CONF.glance_service_type,
            endpoint_region=region_name or CONF.os_region_name,
            endpoint_type=CONF.glance_endpoint_type)

    auth = v3.Token(CONF.trove_auth_url, context.auth_token)
    session = ka_session.Session(auth=auth)

    return Client(CONF.glance_client_version, endpoint=endpoint_url,
                  session=session)


create_glance_client = import_class(CONF.remote_glance_client)
