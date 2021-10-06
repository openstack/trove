=============================================
Manage databases and users on Trove instances
=============================================

Assume that you installed Trove service and uploaded images with datastore of
your choice. This section shows how to manage users and databases in a MySQL
5.7 instance.

Currently, the Database and User API is only supported by mysql datastore.

For database user management, there are two approaches:

1. If the ``root_on_create`` option is enabled for the datastore in trove
   service config file, the root user password is returned after creating
   instance, which can be used directly to access the database.
2. If ``root_on_create=False``, the recommended way is to get root password
   (``POST /v1.0/{project_id}/instances/{instance_id}/root`` or ``openstack
   database root enable`` in CLI) and communicate with the database service
   directly for database and user management.

Manage root user
~~~~~~~~~~~~~~~~

For all the datastores, the user could enable root and get root password for
further database operations.

.. code-block:: console

   $ openstack database root enable f22ce0d9-8c9c-403a-8599-2269761a66de
   +----------+--------------------------------------+
   | Field    | Value                                |
   +----------+--------------------------------------+
   | name     | root                                 |
   | password | I5nPpBj1qf1eGR1idQorj1szppXGpYyYNj4h |
   +----------+--------------------------------------+

If needed, ``openstack database root disable <instance_id>`` command could
disable the root user.

Database and User management via Trove CLI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trove provides API to manage users and databases for mysql datastore.

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

With Trove API you can grant and revoke database access rights for existing
users.

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