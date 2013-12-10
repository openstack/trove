# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

import testtools
from trove.common.pagination import PaginatedDataView


class TestPaginatedDataView(testtools.TestCase):

    def test_creation_with_string_marker(self):
        view = PaginatedDataView("TestType", [], "http://current_page",
                                 next_page_marker="marker")
        self.assertEqual("marker", view.next_page_marker)

    def test_creation_with_none_marker(self):
        view = PaginatedDataView("TestType", [], "http://current_page",
                                 next_page_marker=None)
        self.assertIsNone(view.next_page_marker)

    def test_creation_with_none_string_marker(self):
        view = PaginatedDataView("TestType", [], "http://current_page",
                                 next_page_marker=52)
        self.assertEqual("52", view.next_page_marker)
