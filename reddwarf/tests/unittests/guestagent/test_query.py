#    Copyright 2012 OpenStack Foundation
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
#    under the License

import testtools
from reddwarf.guestagent import query


class QueryTest(testtools.TestCase):
    def setUp(self):
        super(QueryTest, self).setUp()

    def tearDown(self):
        super(QueryTest, self).tearDown()

    def test_columns(self):
        myQuery = query.Query(columns=None)
        self.assertEqual("SELECT *", myQuery._columns)

    def test_columns_2(self):
        columns = ["col_A", "col_B"]
        myQuery = query.Query(columns=columns)
        self.assertEqual("SELECT col_A, col_B", myQuery._columns)

    def test_tables(self):
        tables = ['table_A', 'table_B']
        myQuery = query.Query(tables=tables)
        self.assertEqual("FROM table_A, table_B", myQuery._tables)

    def test_where(self):
        myQuery = query.Query(where=None)
        self.assertEqual("", myQuery._where)

    def test_where_2(self):
        conditions = ['cond_A', 'cond_B']
        myQuery = query.Query(where=conditions)
        self.assertEqual("WHERE cond_A AND cond_B", myQuery._where)

    def test_order(self):
        myQuery = query.Query(order=None)
        self.assertEqual('', myQuery._order)

    def test_order_2(self):
        orders = ['deleted_at', 'updated_at']
        myQuery = query.Query(order=orders)
        self.assertEqual('ORDER BY deleted_at, updated_at', myQuery._order)

    def test_group_by(self):
        myQuery = query.Query(group=None)
        self.assertEqual('', myQuery._group_by)

    def test_group_by_2(self):
        groups = ['deleted=1']
        myQuery = query.Query(group=groups)
        self.assertEqual('GROUP BY deleted=1', myQuery._group_by)

    def test_limit(self):
        myQuery = query.Query(limit=None)
        self.assertEqual('', myQuery._limit)

    def test_limit_2(self):
        limit_count = 20
        myQuery = query.Query(limit=limit_count)
        self.assertEqual('LIMIT 20', myQuery._limit)

    def test_grant_no_arg_constr(self):
        grant = query.Grant()
        self.assertIsNotNone(grant)
        self.assertEqual("GRANT USAGE ON *.* "
                         "TO ``@`%`;",
                         str(grant))

    def test_grant_all_with_grant_option(self):
        permissions = ['ALL']
        user_name = 'root'
        user_password = 'password123'
        host = 'localhost'

        # grant_option defaults to True
        grant = query.Grant(permissions=permissions,
                            user=user_name,
                            host=host,
                            clear=user_password,
                            grant_option=True)

        self.assertEqual("GRANT ALL PRIVILEGES ON *.* TO "
                         "`root`@`localhost` "
                         "IDENTIFIED BY 'password123' "
                         "WITH GRANT OPTION;",
                         str(grant))

    def test_grant_all_with_explicit_grant_option(self):
        permissions = ['ALL', 'GRANT OPTION']
        user_name = 'root'
        user_password = 'password123'
        host = 'localhost'
        grant = query.Grant(permissions=permissions,
                            user=user_name,
                            host=host,
                            clear=user_password,
                            grant_option=True)

        self.assertEqual("GRANT ALL PRIVILEGES ON *.* TO "
                         "`root`@`localhost` "
                         "IDENTIFIED BY 'password123' "
                         "WITH GRANT OPTION;",
                         str(grant))

    def test_grant_specify_permissions(self):
        permissions = ['ALTER ROUTINE',
                       'CREATE',
                       'ALTER',
                       'CREATE ROUTINE',
                       'CREATE TEMPORARY TABLES',
                       'CREATE VIEW',
                       'CREATE USER',
                       'DELETE',
                       'DROP',
                       'EVENT',
                       'EXECUTE',
                       'INDEX',
                       'INSERT',
                       'LOCK TABLES',
                       'PROCESS',
                       'REFERENCES',
                       'SELECT',
                       'SHOW DATABASES',
                       'SHOW VIEW',
                       'TRIGGER',
                       'UPDATE',
                       'USAGE']

        user_name = 'root'
        user_password = 'password123'
        host = 'localhost'
        grant = query.Grant(permissions=permissions,
                            user=user_name,
                            host=host,
                            clear=user_password)

        self.assertEqual("GRANT ALTER, "
                         "ALTER ROUTINE, "
                         "CREATE, "
                         "CREATE ROUTINE, "
                         "CREATE TEMPORARY TABLES, "
                         "CREATE USER, "
                         "CREATE VIEW, "
                         "DELETE, "
                         "DROP, "
                         "EVENT, "
                         "EXECUTE, "
                         "INDEX, "
                         "INSERT, "
                         "LOCK TABLES, "
                         "PROCESS, "
                         "REFERENCES, "
                         "SELECT, "
                         "SHOW DATABASES, "
                         "SHOW VIEW, "
                         "TRIGGER, "
                         "UPDATE, "
                         "USAGE ON *.* TO "
                         "`root`@`localhost` "
                         "IDENTIFIED BY "
                         "'password123';",
                         str(grant))

    def test_grant_specify_duplicate_permissions(self):
        permissions = ['ALTER ROUTINE',
                       'CREATE',
                       'CREATE',
                       'DROP',
                       'DELETE',
                       'DELETE',
                       'ALTER',
                       'CREATE ROUTINE',
                       'CREATE TEMPORARY TABLES',
                       'CREATE VIEW',
                       'CREATE USER',
                       'DELETE',
                       'DROP',
                       'EVENT',
                       'EXECUTE',
                       'INDEX',
                       'INSERT',
                       'LOCK TABLES',
                       'PROCESS',
                       'REFERENCES',
                       'SELECT',
                       'SHOW DATABASES',
                       'SHOW VIEW',
                       'TRIGGER',
                       'UPDATE',
                       'USAGE']

        user_name = 'root'
        user_password = 'password123'
        host = 'localhost'
        grant = query.Grant(permissions=permissions,
                            user=user_name,
                            host=host,
                            clear=user_password)

        self.assertEqual("GRANT ALTER, "
                         "ALTER ROUTINE, "
                         "CREATE, "
                         "CREATE ROUTINE, "
                         "CREATE TEMPORARY TABLES, "
                         "CREATE USER, "
                         "CREATE VIEW, "
                         "DELETE, "
                         "DROP, "
                         "EVENT, "
                         "EXECUTE, "
                         "INDEX, "
                         "INSERT, "
                         "LOCK TABLES, "
                         "PROCESS, "
                         "REFERENCES, "
                         "SELECT, "
                         "SHOW DATABASES, "
                         "SHOW VIEW, "
                         "TRIGGER, "
                         "UPDATE, "
                         "USAGE ON *.* TO "
                         "`root`@`localhost` "
                         "IDENTIFIED BY "
                         "'password123';",
                         str(grant))
