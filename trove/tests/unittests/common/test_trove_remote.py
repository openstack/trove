# Copyright 2024 Bizfly Cloud, Inc.
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
#


from trove.common import cfg
from trove.common.clients import normalize_url
from trove.common import context
from trove.common import timeutils
from trove.common import trove_remote
from trove.tests.unittests import trove_testtools

CONF = cfg.CONF


class TestTroveClient(trove_testtools.TestCase):
    def setUp(self):
        super(TestTroveClient, self).setUp()
        self.context = context.TroveContext(
            project_id='TENANT-' + str(timeutils.utcnow()),
            user='USER-' + str(timeutils.utcnow()),
            auth_token='AUTH_TOKEN-' + str(timeutils.utcnow()))

    def test_trove_with_remote_client(self):
        self.patch_conf_property('trove_url', 'trove_url')
        client = trove_remote.trove_client(self.context)
        url = '%(url)s%(tenant)s' % {
            'url': normalize_url(CONF.trove_url),
            'tenant': self.context.project_id}
        self.assertEqual(url, client.client.management_url)
