=================
Upgrade datastore
=================

You can upgrade the datastore version of the database instance. When you
perform an upgrade, the system automatically manages data and
configuration files of your database.

To perform datastore upgrade, you need:

- A Trove database instance to be upgrade.
- A guest image with the target datastore version.

This guide shows you how to upgrade MySQL datastore from 5.7.29 to 5.7.30 for a
database instance.

.. warning::

   Datastore upgrade could cause downtime of the database service.

Upgrading datastore
~~~~~~~~~~~~~~~~~~~

#. **Check datastore versions in the system**

   In my environment, both datastore version 5.7.29 and 5.7.30 are defined for
   MySQL.

   .. code-block:: console

      $ openstack datastore list
      +--------------------------------------+-------+
      | ID                                   | Name  |
      +--------------------------------------+-------+
      | 50bed39d-6788-4a0d-8d74-321012bb6b55 | mysql |
      +--------------------------------------+-------+
      $ openstack datastore version list mysql
      +--------------------------------------+--------+
      | ID                                   | Name   |
      +--------------------------------------+--------+
      | 70c68d0a-27e1-4fbd-bd3b-f29d42ce1a7d | 5.7.29 |
      | cf91aa9a-2192-4ec4-b7ce-5cac3b1e7dbe | 5.7.30 |
      +--------------------------------------+--------+

#. **Create a new instance with datastore version 5.7.29**

   Make sure the instance status is HEALTHY before upgrading.

   .. code-block:: console

      $ openstack database instance create test-mysql-upgrade \
        --flavor d2 \
        --size 1 \
        --nic net-id=$netid \
        --datastore mysql --datastore_version 5.7.29 \
        --databases testdb --users user:password
      $ openstack database instance list
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      | ID                                   | Name               | Datastore | Datastore Version | Status  | Addresses                                     | Flavor ID | Size | Region    | Role    |
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      | 32eb56b0-d10d-43e9-b59e-1e4b0979e5dd | test-mysql-upgrade | mysql     | 5.7.29            | HEALTHY | [{'address': '10.0.0.54', 'type': 'private'}] | d2        |    1 | RegionOne |         |
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+

   Check the MySQL version by connecting with the database:

   .. code-block:: console

      $ ip=10.0.0.54
      $ mysql -u user -ppassword -h $ip testdb
      mysql> SELECT @@GLOBAL.innodb_version;
      +-------------------------+
      | @@GLOBAL.innodb_version |
      +-------------------------+
      | 5.7.29                  |
      +-------------------------+

#. **Run upgrade**

   Use :command:`openstack database instance upgrade` command to upgrade the
   datastore of the instance.

   .. code-block:: console

      $ openstack database instance upgrade 32eb56b0-d10d-43e9-b59e-1e4b0979e5dd cf91aa9a-2192-4ec4-b7ce-5cac3b1e7dbe

#. **Wait until status changes from UPGRADE to HEALTHY**

   Use :command:`openstack database instance list` to check the
   current status.

   .. code-block:: console

      $ openstack database instance list
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      | ID                                   | Name               | Datastore | Datastore Version | Status  | Addresses                                     | Flavor ID | Size | Region    | Role    |
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      | 32eb56b0-d10d-43e9-b59e-1e4b0979e5dd | test-mysql-upgrade | mysql     | 5.7.30            | UPGRADE | [{'address': '10.0.0.54', 'type': 'private'}] | d2        |    1 | RegionOne |         |
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      $ openstack database instance list
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      | ID                                   | Name               | Datastore | Datastore Version | Status  | Addresses                                     | Flavor ID | Size | Region    | Role    |
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+
      | 32eb56b0-d10d-43e9-b59e-1e4b0979e5dd | test-mysql-upgrade | mysql     | 5.7.30            | HEALTHY | [{'address': '10.0.0.54', 'type': 'private'}] | d2        |    1 | RegionOne |         |
      +--------------------------------------+--------------------+-----------+-------------------+---------+-----------------------------------------------+-----------+------+-----------+---------+

   Check the MySQL version again:

   .. code-block:: console

      $ mysql -u user -ppassword -h $ip testdb
      mysql> SELECT @@GLOBAL.innodb_version;
      +-------------------------+
      | @@GLOBAL.innodb_version |
      +-------------------------+
      | 5.7.30                  |
      +-------------------------+
