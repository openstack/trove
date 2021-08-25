# Copyright 2021 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from unittest import mock

from trove.common import exception
from trove.common import wsgi
from trove.extensions.mgmt.quota import service as quota_service
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestQuotaController(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()
        cls.controller = quota_service.QuotaController()
        cls.admin_project_id = cls.random_uuid()
        super(TestQuotaController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()
        super(TestQuotaController, cls).tearDownClass()

    def test_show_admin_query(self):
        user_project_id = self.random_uuid()
        req_mock = mock.MagicMock(
            environ={
                wsgi.CONTEXT_KEY: mock.MagicMock(
                    project_id=self.admin_project_id,
                    is_admin=True
                )
            }
        )
        result = self.controller.show(req_mock, self.admin_project_id,
                                      user_project_id)

        self.assertEqual(200, result.status)

    def test_show_user_query(self):
        """Show the tenant's own quota."""
        user_project_id = self.random_uuid()
        req_mock = mock.MagicMock(
            environ={
                wsgi.CONTEXT_KEY: mock.MagicMock(
                    is_admin=False
                )
            }
        )
        result = self.controller.show(req_mock, user_project_id,
                                      user_project_id)

        self.assertEqual(200, result.status)

    def test_show_user_query_not_allowed(self):
        """Show other tenant's quota should fail."""
        user_project_id = self.random_uuid()
        req_mock = mock.MagicMock(
            environ={
                wsgi.CONTEXT_KEY: mock.MagicMock(
                    is_admin=False
                )
            }
        )
        self.assertRaises(
            exception.TroveOperationAuthError,
            self.controller.show,
            req_mock, user_project_id,
            self.random_uuid()
        )
