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

import webob

from trove.common import auth
from trove.tests.unittests import trove_testtools


class TestAuth(trove_testtools.TestCase):
    def test_unicode_characters_in_headers(self):
        middleware = auth.AuthorizationMiddleware(
            "test_trove",
            [auth.TenantBasedAuth()])
        tenant_id = 'test_tenant_id'
        url = '/%s/instances' % tenant_id
        req = webob.Request.blank(url)

        # test string with chinese characters
        test_str = u'\u6d4b\u8bd5'
        req.headers = {
            'X-Tenant-ID': tenant_id,
            'X-Auth-Project-Id': test_str
        }
        # invocation
        middleware.process_request(req)
