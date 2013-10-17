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
