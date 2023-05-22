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

from trove.guestagent.datastore.postgres import service
from trove.tests.unittests import trove_testtools

statement = (
    "SELECT usename FROM pg_catalog.pg_user WHERE usesuper = true"
)
username = "postgres"
port = 5432
result = [(1, "one"), (2, 'two'), (3, 'three')]


class TestPostgresConnection(trove_testtools.TestCase):
    def setUp(self):
        super(TestPostgresConnection, self).setUp()

    # execute is expected to returns nothing
    @mock.patch(
        'trove.guestagent.datastore.postgres.service.PostgresConnection')
    def test_execute(self, mock_postgres_connection):
        postgres_connection = mock.MagicMock()
        postgres_connection.execute = mock.MagicMock(return_value=None)
        mock_postgres_connection.return_value = postgres_connection

        # assertion here
        connection = service.PostgresConnection(username, port=port)
        self.assertIsNone(connection.execute(statement),
                          'postgres_connection_execute does not returns None')

    # query is expected to returns result
    @mock.patch(
        'trove.guestagent.datastore.postgres.service.PostgresConnection')
    def test_query(self, mock_postgres_connection):
        postgres_connection = mock.MagicMock()
        postgres_connection.query = mock.MagicMock(return_value=result)
        mock_postgres_connection.return_value = postgres_connection

        # assertion here
        connection = service.PostgresConnection(username, port=port)
        self.assertEqual(result, connection.query(statement),
                         'postgres_connection_query does not returns expected')
