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
#    under the License.

import testtools
from trove.guestagent.common import sql_query


class QueryTestBase(testtools.TestCase):
    def setUp(self):
        super(QueryTestBase, self).setUp()

    def tearDown(self):
        super(QueryTestBase, self).tearDown()


class QueryTest(QueryTestBase):
    def setUp(self):
        super(QueryTest, self).setUp()

    def tearDown(self):
        super(QueryTest, self).tearDown()

    def test_columns(self):
        myQuery = sql_query.Query(columns=None)
        self.assertEqual("SELECT *", myQuery._columns)

    def test_columns_2(self):
        columns = ["col_A", "col_B"]
        myQuery = sql_query.Query(columns=columns)
        self.assertEqual("SELECT col_A, col_B", myQuery._columns)

    def test_tables(self):
        tables = ['table_A', 'table_B']
        myQuery = sql_query.Query(tables=tables)
        self.assertEqual("FROM table_A, table_B", myQuery._tables)

    def test_where(self):
        myQuery = sql_query.Query(where=None)
        self.assertEqual("", myQuery._where)

    def test_where_2(self):
        conditions = ['cond_A', 'cond_B']
        myQuery = sql_query.Query(where=conditions)
        self.assertEqual("WHERE cond_A AND cond_B", myQuery._where)

    def test_order(self):
        myQuery = sql_query.Query(order=None)
        self.assertEqual('', myQuery._order)

    def test_order_2(self):
        orders = ['deleted_at', 'updated_at']
        myQuery = sql_query.Query(order=orders)
        self.assertEqual('ORDER BY deleted_at, updated_at', myQuery._order)

    def test_group_by(self):
        myQuery = sql_query.Query(group=None)
        self.assertEqual('', myQuery._group_by)

    def test_group_by_2(self):
        groups = ['deleted=1']
        myQuery = sql_query.Query(group=groups)
        self.assertEqual('GROUP BY deleted=1', myQuery._group_by)

    def test_limit(self):
        myQuery = sql_query.Query(limit=None)
        self.assertEqual('', myQuery._limit)

    def test_limit_2(self):
        limit_count = 20
        myQuery = sql_query.Query(limit=limit_count)
        self.assertEqual('LIMIT 20', myQuery._limit)


class GrantTest(QueryTestBase):
    def setUp(self):
        super(GrantTest, self).setUp()

    def tearDown(self):
        super(GrantTest, self).tearDown()

    def test_grant_no_arg_constr(self):
        grant = sql_query.Grant()
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
        grant = sql_query.Grant(permissions=permissions,
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
        grant = sql_query.Grant(permissions=permissions,
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
        grant = sql_query.Grant(permissions=permissions,
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
        grant = sql_query.Grant(permissions=permissions,
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


class RevokeTest(QueryTestBase):
    def setUp(self):
        super(RevokeTest, self).setUp()

    def tearDown(self):
        super(RevokeTest, self).tearDown()

    def test_defaults(self):
        r = sql_query.Revoke()
        # Technically, this isn't valid for MySQL.
        self.assertEqual(str(r), "REVOKE ALL ON *.* FROM ``@`%`;")

    def test_permissions(self):
        r = sql_query.Revoke()
        r.user = 'x'
        r.permissions = ['CREATE', 'DELETE', 'DROP']
        self.assertEqual(str(r),
                         "REVOKE CREATE, DELETE, DROP ON *.* FROM `x`@`%`;")

    def test_database(self):
        r = sql_query.Revoke()
        r.user = 'x'
        r.database = 'foo'
        self.assertEqual(str(r), "REVOKE ALL ON `foo`.* FROM `x`@`%`;")

    def test_table(self):
        r = sql_query.Revoke()
        r.user = 'x'
        r.database = 'foo'
        r.table = 'bar'
        self.assertEqual(str(r), "REVOKE ALL ON `foo`.'bar' FROM `x`@`%`;")

    def test_user(self):
        r = sql_query.Revoke()
        r.user = 'x'
        self.assertEqual(str(r), "REVOKE ALL ON *.* FROM `x`@`%`;")

    def test_user_host(self):
        r = sql_query.Revoke()
        r.user = 'x'
        r.host = 'y'
        self.assertEqual(str(r), "REVOKE ALL ON *.* FROM `x`@`y`;")


class CreateDatabaseTest(QueryTestBase):
    def setUp(self):
        super(CreateDatabaseTest, self).setUp()

    def tearDown(self):
        super(CreateDatabaseTest, self).tearDown()

    def test_defaults(self):
        cd = sql_query.CreateDatabase('foo')
        self.assertEqual(str(cd), "CREATE DATABASE IF NOT EXISTS `foo`;")

    def test_charset(self):
        cd = sql_query.CreateDatabase('foo')
        cd.charset = "foo"
        self.assertEqual(str(cd), ("CREATE DATABASE IF NOT EXISTS `foo` "
                                   "CHARACTER SET = 'foo';"))

    def test_collate(self):
        cd = sql_query.CreateDatabase('foo')
        cd.collate = "bar"
        self.assertEqual(str(cd), ("CREATE DATABASE IF NOT EXISTS `foo` "
                                   "COLLATE = 'bar';"))


class DropDatabaseTest(QueryTestBase):
    def setUp(self):
        super(DropDatabaseTest, self).setUp()

    def tearDown(self):
        super(DropDatabaseTest, self).tearDown()

    def test_defaults(self):
        dd = sql_query.DropDatabase('foo')
        self.assertEqual(str(dd), "DROP DATABASE `foo`;")


class CreateUserTest(QueryTestBase):
    def setUp(self):
        super(CreateUserTest, self).setUp()

    def tearDown(self):
        super(CreateUserTest, self).tearDown()

    def test_defaults(self):
        username = 'root'
        hostname = 'localhost'
        password = 'password123'
        cu = sql_query.CreateUser(user=username, host=hostname, clear=password)
        self.assertEqual(str(cu), "CREATE USER :user@:host "
                                  "IDENTIFIED BY 'password123';")


class UpdateUserTest(QueryTestBase):
    def setUp(self):
        super(UpdateUserTest, self).setUp()

    def tearDown(self):
        super(UpdateUserTest, self).tearDown()

    def test_rename_user(self):
        username = 'root'
        hostname = 'localhost'
        new_user = 'root123'
        uu = sql_query.UpdateUser(user=username, host=hostname,
                                  new_user=new_user)
        self.assertEqual(str(uu), "UPDATE mysql.user SET User='root123' "
                                  "WHERE User = 'root' "
                                  "AND Host = 'localhost';")

    def test_change_password(self):
        username = 'root'
        hostname = 'localhost'
        new_password = 'password123'
        uu = sql_query.UpdateUser(user=username, host=hostname,
                                  clear=new_password)
        self.assertEqual(str(uu), "UPDATE mysql.user SET "
                                  "Password=PASSWORD('password123') "
                                  "WHERE User = 'root' "
                                  "AND Host = 'localhost';")

    def test_change_host(self):
        username = 'root'
        hostname = 'localhost'
        new_host = '%'
        uu = sql_query.UpdateUser(user=username, host=hostname,
                                  new_host=new_host)
        self.assertEqual(str(uu), "UPDATE mysql.user SET Host='%' "
                                  "WHERE User = 'root' "
                                  "AND Host = 'localhost';")

    def test_change_password_and_username(self):
        username = 'root'
        hostname = 'localhost'
        new_user = 'root123'
        new_password = 'password123'
        uu = sql_query.UpdateUser(user=username, host=hostname,
                                  clear=new_password, new_user=new_user)
        self.assertEqual(str(uu), "UPDATE mysql.user SET User='root123', "
                                  "Password=PASSWORD('password123') "
                                  "WHERE User = 'root' "
                                  "AND Host = 'localhost';")

    def test_change_username_password_hostname(self):
        username = 'root'
        hostname = 'localhost'
        new_user = 'root123'
        new_password = 'password123'
        new_host = '%'
        uu = sql_query.UpdateUser(user=username, host=hostname,
                                  clear=new_password, new_user=new_user,
                                  new_host=new_host)
        self.assertEqual(str(uu), "UPDATE mysql.user SET User='root123', "
                                  "Host='%', "
                                  "Password=PASSWORD('password123') "
                                  "WHERE User = 'root' "
                                  "AND Host = 'localhost';")

    def test_change_username_and_hostname(self):
        username = 'root'
        hostname = 'localhost'
        new_user = 'root123'
        new_host = '%'
        uu = sql_query.UpdateUser(user=username, host=hostname,
                                  new_host=new_host, new_user=new_user)
        self.assertEqual(str(uu), "UPDATE mysql.user SET User='root123', "
                                  "Host='%' "
                                  "WHERE User = 'root' "
                                  "AND Host = 'localhost';")


class DropUserTest(QueryTestBase):
    def setUp(self):
        super(DropUserTest, self).setUp()

    def tearDown(self):
        super(DropUserTest, self).tearDown()

    def test_defaults(self):
        username = 'root'
        hostname = 'localhost'
        du = sql_query.DropUser(user=username, host=hostname)
        self.assertEqual(str(du), "DROP USER `root`@`localhost`;")
