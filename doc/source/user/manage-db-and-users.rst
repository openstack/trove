=============================================
Manage databases and users on Trove instances
=============================================

Assume that you installed Trove service and uploaded images with datastore
of your choice.
This section shows how to manage users and databases in a MySQL 5.7 instance.

Add new database and user to an existing Trove instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trove provides API to manage users and databases on
datastores including relational (e.g. MySQL, PostgreSQL) and non-relational
(e.g. Redis, Cassandra). Once a Trove instance with a datastore of choice is
active you can use Trove API to create new databases and/or users.

.. code-block:: console

  $ openstack database user list db-instance

    +------+------+-----------+
    | Name | Host | Databases |
    +------+------+-----------+
    | test | %    | testdb    |
    +------+------+-----------+

  $ openstack database user create db-instance newuser userpass --databases testdb

  $ openstack database user list db-instance

    +---------+------+-----------+
    | Name    | Host | Databases |
    +---------+------+-----------+
    | newuser | %    | testdb    |
    | test    | %    | testdb    |
    +---------+------+-----------+


  $ mysql -h 172.24.4.199 -u newuser -p testdb
    Enter password:

    mysql> show databases;

    +--------------------+
    | Database           |
    +--------------------+
    | information_schema |
    | testdb             |
    +--------------------+

    2 rows in set (0.00 sec)


  $ openstack database db create db-instance newdb


  $ openstack database db list db-instance

    +--------+
    | Name   |
    +--------+
    | newdb  |
    | sys    |
    | testdb |
    +--------+

  $ mysql -h 172.24.4.199 -u newuser -p newdb

    Enter password:
    ERROR 1044 (42000): Access denied for user 'newuser'@'%' to database 'newdb'


Manage access to databases
~~~~~~~~~~~~~~~~~~~~~~~~~~

With Trove API you can grant and revoke database access rights for existing users.

.. code-block:: console

  $ openstack database user grant access db-instance newuser newdb


  $ openstack database user show access db-instance newuser

    +--------+
    | Name   |
    +--------+
    | newdb  |
    | testdb |
    +--------+

  $ mysql -h IP_ADDRESS -u newuser -p newdb
    Enter password:


  $ openstack database user show access db-instance test

    +--------+
    | Name   |
    +--------+
    | testdb |
    +--------+

  $ mysql -h IP_ADDRESS -u test -p newdb
    Enter password:

    ERROR 1044 (42000): Access denied for user 'test'@'%' to database 'newdb'


  $ openstack database user revoke access db-instance newuser newdb


  $ mysql -h IP_ADDRESS -u newuser -p newdb
    Enter password:

    ERROR 1044 (42000): Access denied for user 'newuser'@'%' to database 'newdb'


Delete databases
~~~~~~~~~~~~~~~~

Lastly, Trove provides API for deleting databases.

.. code-block:: console

  $ openstack database db list db-instance

    +--------+
    | Name   |
    +--------+
    | newdb  |
    | sys    |
    | testdb |
    +--------+

  $ openstack database db delete db-instance testdb

  $ openstack database db list db-instance

    +--------+
    | Name   |
    +--------+
    | newdb  |
    | sys    |
    +--------+

  $ mysql -h IP_ADDRESS -u test -p testdb
    Enter password:

    ERROR 1049 (42000): Unknown database 'testdb'