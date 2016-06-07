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

from mock import Mock

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
        return pagination.paginate_list(li, limit=limit, marker=marker,
                                        include_marker=include_marker)

    def test_paginate_list(self):
        # start list
        li_1, marker_1 = self._do_paginate_list(limit=2)
        self.assertEqual(['a', 'b'], li_1)
        self.assertEqual('b', marker_1)

        # continue list, do not include marker in result
        li_2, marker_2 = self._do_paginate_list(limit=2, marker=marker_1)
        self.assertEqual(['c', 'd'], li_2)
        self.assertEqual('d', marker_2)
        li_3, marker_3 = self._do_paginate_list(limit=2, marker=marker_2)
        self.assertEqual(['e'], li_3)
        self.assertIsNone(marker_3)

        # alternate continue list, include marker in result
        li_4, marker_4 = self._do_paginate_list(limit=2, marker=marker_1,
                                                include_marker=True)
        self.assertEqual(['b', 'c'], li_4)
        self.assertEqual('c', marker_4)
        li_5, marker_5 = self._do_paginate_list(limit=2, marker=marker_4,
                                                include_marker=True)
        self.assertEqual(['c', 'd'], li_5)
        self.assertEqual('d', marker_5)
        li_6, marker_6 = self._do_paginate_list(limit=2, marker=marker_5,
                                                include_marker=True)
        self.assertEqual(['d', 'e'], li_6)
        self.assertIsNone(marker_6)

        # bad marker
        li_4, marker_4 = self._do_paginate_list(marker='f')
        self.assertEqual([], li_4)
        self.assertIsNone(marker_4)

        li_5, marker_5 = self._do_paginate_list(limit=1, marker='f')
        self.assertEqual([], li_5)
        self.assertIsNone(marker_5)

    def test_dict_paginate(self):
        li = [{'_collate': 'en_US.UTF-8',
               '_character_set': 'UTF8',
               '_name': 'db1'},
              {'_collate': 'en_US.UTF-8',
               '_character_set': 'UTF8',
               '_name': 'db3'},
              {'_collate': 'en_US.UTF-8',
               '_character_set': 'UTF8',
               '_name': 'db2'},
              {'_collate': 'en_US.UTF-8',
               '_character_set': 'UTF8',
               '_name': 'db5'},
              {'_collate': 'en_US.UTF-8',
               '_character_set': 'UTF8',
               '_name': 'db4'}
              ]

        l, m = pagination.paginate_dict_list(li, '_name', limit=1,
                                             marker='db1',
                                             include_marker=True)
        self.assertEqual(l[0], li[0])
        self.assertEqual(m, 'db1')

    def test_object_paginate(self):

        def build_mock_object(name):
            o = Mock()
            o.name = name
            o.attr = 'attr'
            return o

        li = [build_mock_object('db1'), build_mock_object('db2'),
              build_mock_object('db3')]

        l, m = pagination.paginate_object_list(li, 'name', limit=1,
                                               marker='db1',
                                               include_marker=True)
        self.assertEqual(l[0], li[0])
        self.assertEqual(m, 'db1')
