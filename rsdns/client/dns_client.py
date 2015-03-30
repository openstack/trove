# Copyright 2011 OpenStack Foundation
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

"""
DNS Client interface. Child of OpenStack client to handle auth issues.
We have to duplicate a lot of code from the OpenStack client since so much
is different here.
"""

from trove.openstack.common import log as logging

import exceptions

try:
    import json
except ImportError:
    import simplejson as json


from novaclient.client import HTTPClient
from novaclient.v2.client import Client

LOG = logging.getLogger('rsdns.client.dns_client')


class DNSaasClient(HTTPClient):

    def __init__(self, accountId, user, apikey, auth_url, management_base_url):
        tenant = "dbaas"
        super(DNSaasClient, self).__init__(user, apikey, tenant, auth_url)
        self.accountId = accountId
        self.management_base_url = management_base_url
        self.api_key = apikey
        self.disable_ssl_certificate_validation = True
        self.service = "cloudDNS"

    def authenticate(self):
        """Set the management url and auth token"""
        req_body = {'credentials': {'username': self.user,
                                    'key': self.api_key}}
        resp, body = self.request(self.auth_url, "POST", body=req_body)
        if 'access' in body:
            if not self.management_url:
                # Assume the new Keystone lite:
                catalog = body['access']['serviceCatalog']
                for service in catalog:
                    if service['name'] == self.service:
                        self.management_url = service['adminURL']
            self.auth_token = body['access']['token']['id']
        else:
            # Assume pre-Keystone Light:
            try:
                if not self.management_url:
                    keys = ['auth',
                            'serviceCatalog',
                            self.service,
                            0,
                            'publicURL']
                    url = body
                    for key in keys:
                        url = url[key]
                    self.management_url = url
                self.auth_token = body['auth']['token']['id']
            except KeyError:
                raise NotImplementedError("Service: %s is not available"
                % self.service)

    def request(self, *args, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        kwargs['headers']['User-Agent'] = self.USER_AGENT
        kwargs['headers']['Accept'] = 'application/json'
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])
            LOG.debug("REQ HEADERS:" + str(kwargs['headers']))
            LOG.debug("REQ BODY:" + str(kwargs['body']))

        resp, body = super(HTTPClient, self).request(*args, **kwargs)

        self.http_log(args, kwargs, resp, body)

        if body:
            try:
                body = json.loads(body)
            except ValueError:
                pass
        else:
            body = None

        if resp.status in (400, 401, 403, 404, 408, 409, 413, 500, 501):
            raise exceptions.from_response(resp, body)

        return resp, body


class DNSaas(Client):
    """
    Top-level object to access the DNSaas service
    """

    def __init__(self, accountId, username, apikey,
                 auth_url='https://auth.api.rackspacecloud.com/v1.0',
                 management_base_url=None):
        from rsdns.client.dns_client import DNSaasClient
        from rsdns.client.domains import DomainsManager
        from rsdns.client.records import RecordsManager

        super(DNSaas, self).__init__(self, accountId, username, apikey,
                                     auth_url, management_base_url)
        self.client = DNSaasClient(accountId, username, apikey, auth_url,
                                    management_base_url)
        self.domains = DomainsManager(self)
        self.records = RecordsManager(self)
