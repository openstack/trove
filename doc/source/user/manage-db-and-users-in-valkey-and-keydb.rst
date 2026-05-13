.. _manage_db_and_users_in_valkey_and_keydb:

==========================================
Manage users on KeyDB and Valkey instances
==========================================

KeyDB and Valkey use Redis ACLs for access control. Unlike relational
datastores such as MySQL, Trove databases in KeyDB and Valkey do not represent
separate logical databases created by users.

Instead, Trove exposes the available Redis ACL command categories through the
Database and User API. These categories can be assigned to users to control
which categories of Redis commands they are allowed to execute.

Manage users
~~~~~~~~~~~~

Users can be created using the same Trove CLI commands as for other supported
datastores. The ``--databases`` option specifies the ACL categories that should
be granted to the user.

.. code-block:: console

    $ openstack database user create keydb-instance newuser userpass \
        --databases read write

    $ openstack database user list keydb-instance
    +---------+------+---------------+
    | Name    | Host | Databases     |
    +---------+------+---------------+
    | newuser |      | read, write   |
    +---------+------+---------------+

The ``Host`` field is not applicable to KeyDB or Valkey because Redis ACLs are
not associated with a client hostname.

Users can authenticate directly against the datastore using their username and
password.

.. code-block:: console

    $ redis-cli --user newuser --pass userpass
    127.0.0.1:6379> SET mykey value
    OK
    127.0.0.1:6379> GET mykey
    "value"

Available access categories
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The available categories can be listed using the Trove Database API.

.. code-block:: console

    $ openstack database db list keydb-instance
    +-------------+
    | Name        |
    +-------------+
    | read        |
    | write       |
    | keyspace    |
    | connection  |
    | ...         |
    +-------------+

The exact list of available categories depends on the datastore implementation
and version.

These entries do not represent actual KeyDB or Valkey databases. They represent
Redis ACL command categories.

Manage user access
~~~~~~~~~~~~~~~~~~

Access to additional command categories can be granted to an existing user.

.. code-block:: console

    $ openstack database user grant access keydb-instance newuser keyspace

    $ openstack database user show access keydb-instance newuser
    +-------------+
    | Name        |
    +-------------+
    | read        |
    | write       |
    | keyspace    |
    +-------------+

Access can also be revoked.

.. code-block:: console

    $ openstack database user revoke access keydb-instance newuser keyspace

    $ openstack database user show access keydb-instance newuser
    +--------+
    | Name   |
    +--------+
    | read   |
    | write  |
    +--------+

Database management
~~~~~~~~~~~~~~~~~~~

KeyDB and Valkey do not support creating or deleting databases through the
Trove Database API.

The ``database create`` and ``database delete`` operations are therefore not
applicable to these datastores. The database list is provided only to expose
the available Redis ACL categories that can be assigned to users.

Manage root user
~~~~~~~~~~~~~~~~

The root user can be enabled and disabled using the standard Trove commands.

.. code-block:: console

    $ openstack database root enable keydb-instance
    +----------+--------------------------------------+
    | Field    | Value                                |
    +----------+--------------------------------------+
    | name     | root                                 |
    | password | I5nPpBj1qf1eGR1idQorj1szppXGpYyYNj4h |
    +----------+--------------------------------------+

The root user has unrestricted access to the datastore.

If needed, the root user can be disabled.

.. code-block:: console

    $ openstack database root disable keydb-instance
