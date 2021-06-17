# Copyright 2020 Catalyst Cloud
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
import psycopg2


class PostgresConnection(object):
    def __init__(self, user, password='', host='/var/run/postgresql',
                 port=5432):
        """Utility class to communicate with PostgreSQL.

        Connect with socket rather than IP or localhost address to avoid
        manipulation of pg_hba.conf when the database is running inside
        container with bridge network.

        This class is consistent with PostgresConnection in
        trove/guestagent/datastore/postgres/service.py
        """
        self.user = user
        self.password = password
        self.host = host
        self.port = port

        self.connect_str = (f"user='{self.user}' password='{self.password}' "
                            f"host='{self.host}' port='{self.port}'")

    def __enter__(self, autocommit=False):
        self.conn = psycopg2.connect(self.connect_str)
        self.conn.autocommit = autocommit
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.close()

    def execute(self, statement, identifiers=None, data_values=None):
        """Execute a non-returning statement."""
        self._execute_stmt(statement, identifiers, data_values, False)

    def query(self, query, identifiers=None, data_values=None):
        """Execute a query and return the result set."""
        return self._execute_stmt(query, identifiers, data_values, True)

    def _execute_stmt(self, statement, identifiers, data_values, fetch):
        cmd = self._bind(statement, identifiers)
        with self.conn.cursor() as cursor:
            cursor.execute(cmd, data_values)
            if fetch:
                return cursor.fetchall()

    def _bind(self, statement, identifiers):
        if identifiers:
            return statement.format(*identifiers)
        return statement
