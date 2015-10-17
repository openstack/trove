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
from trove.common import pagination
from trove.tests.unittests import trove_testtools


class TestPaginatedDataView(trove_testtools.TestCase):

    def test_creation_with_string_marker(self):
        view = pagination.PaginatedDataView("TestType", [],
                                            "http://current_page",
                                            next_page_marker="marker")
        self.assertEqual("marker", view.next_page_marker)

    def test_creation_with_none_marker(self):
        view = pagination.PaginatedDataView("TestType", [],
                                            "http://current_page",
                                            next_page_marker=None)
        self.assertIsNone(view.next_page_marker)

    def test_creation_with_none_string_marker(self):
        view = pagination.PaginatedDataView("TestType", [],
                                            "http://current_page",
                                            next_page_marker=52)
        self.assertEqual("52", view.next_page_marker)

    def _do_paginate_list(self, limit=None, marker=None, include_marker=False):
        li = ['a', 'b', 'c', 'd', 'e']
        return pagination.paginate_list(li, limit, marker, include_marker)

    def test_paginate_list(self):
        # start list
        li_1, marker_1 = self._do_paginate_list(limit=2)
        self.assertEqual(['a', 'b'], li_1)
        self.assertEqual('c', marker_1)

        # continue list, do not include marker in result
        li_2, marker_2 = self._do_paginate_list(limit=2, marker=marker_1)
        self.assertEqual(['d', 'e'], li_2)
        self.assertIsNone(marker_2)

        # alternate continue list, include marker in result
        li_3, marker_3 = self._do_paginate_list(limit=2, marker=marker_1,
                                                include_marker=True)
        self.assertEqual(['c', 'd'], li_3)
        self.assertEqual('e', marker_3)

        # bad marker
        li_4, marker_4 = self._do_paginate_list(marker='f')
        self.assertEqual([], li_4)
        self.assertIsNone(marker_4)
