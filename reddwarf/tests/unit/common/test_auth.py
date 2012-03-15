# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright 2012 OpenStack LLC.
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

import unittest

from reddwarf.common.auth import TenantBasedAuth


class TenantRegexTest(unittest.TestCase):

    def check(self, path, no_match=False, expected_tenant_id=None,
              expected_version_id=None):
        print("Path=%s" % path)
        match = TenantBasedAuth.tenant_scoped_url.match(path)
        if no_match:
            self.assertIsNone(match, "Somehow path %s was a match!" % path)
        else:
            self.assertIsNotNone(match)
            if expected_tenant_id:
                actual = match.group('tenant_id')
                self.assertEqual(expected_tenant_id, actual)
            else:
                self.assertRaises(IndexError, match.group('tenant_id'))

    def test_no_match(self):
        self.check("blah", no_match=True)

    def test_has_tenant_id1(self):
        self.check("/mgmt/instances/None", expected_tenant_id="mgmt")

    def test_has_tenant_id2(self):
        self.check(
            "/9bbf90bc162d4d1ea458af6214a625e6/mgmt/instances/None",
            expected_tenant_id="9bbf90bc162d4d1ea458af6214a625e6")
