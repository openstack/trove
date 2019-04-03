=================
Upgrade datastore
=================

You can upgrade your datastore version. When you perform an upgrade,
the system automatically manages data and configuration files of your
database.

To perform datastore upgrade, you need:

- A supported OS image with the target datastore version.

- A Trove database instance to be upgrade.

This example shows you how to upgrade Redis datastore (version 3.2.6)
for a single instance database.

.. note::

   **Before** you begin make sure that:

   -  Your target datastore is binary compatible with the current
      datastore. Each database provider has its own compatibilty
      policy. Usually there shouldn't be any problem when
      performing an upgrade within minor versions.

   -  You **do not** downgrade your datastore.

   -  Target versions is supported by Trove. For instance, Trove
      doesn't support Cassandra >=2.2 at this moment so you
      shouldn't perform an upgrade from 2.1 to 2.2.

Upgrading datastore
~~~~~~~~~~~~~~~~~~~

#. **Check instance status**

   Use :command:`openstack database instance list` to check whether the
   status of your instance is ACTIVE.

   .. code-block:: console

      $openstack database instance list
       +--------------------------------------+------------+-----------+-------------------+--------+-----------+------+-----------+
       | ID                                   | Name       | Datastore | Datastore Version | Status | Flavor ID | Size | Region    |
       +--------------------------------------+------------+-----------+-------------------+--------+-----------+------+-----------+
       | 55411e95-1670-497f-8d92-0179f3b4fdd4 | redis_test | redis     | 3.2.6             | ACTIVE | 6         |    5 | RegionOne |
       +--------------------------------------+------------+-----------+-------------------+--------+-----------+------+-----------+

#. **Check if target version is available**

   Use :command:`openstack datastore version list` command to list
   all available versions your datastore.

   .. code-block:: console

      $openstack datastore version list redis
       +--------------------------------------+-------+
       | ID                                   | Name  |
       +--------------------------------------+-------+
       | 483debec-b7c3-4167-ab1d-1765795ed7eb | 3.2.6 |
       | 507f666e-193c-4194-9d9d-da8342dcb4f1 | 3.2.7 |
       +--------------------------------------+-------+

#. **Run upgrade**

   Use :command:`openstack database instance` command to upgrade your
   datastore for the selected instance.

   .. code-block:: console

      $openstack database instance 55411e95-1670-497f-8d92-0179f3b4fdd4 3.2.7

#. **Wait until status changes from UPGRADE to ACTIVE**

   You can use :command:`openstack database instance list` to check the
   current status.

   .. code-block:: console

      $openstack database instance list
       +--------------------------------------+------------+-----------+-------------------+---------+-----------+------+-----------+
       | ID                                   | Name       | Datastore | Datastore Version | Status  | Flavor ID | Size | Region    |
       +--------------------------------------+------------+-----------+-------------------+---------+-----------+------+-----------+
       | 55411e95-1670-497f-8d92-0179f3b4fdd4 | redis_test | redis     | 3.2.7             | UPGRADE | 6         |    5 | RegionOne |
       +--------------------------------------+------------+-----------+-------------------+---------+-----------+------+-----------+

Other datastores
~~~~~~~~~~~~~~~~

Upgrade for other datastores works in the same way. Currently Trove
supports upgrades for the following datastores:

- MySQL,
- MariaDB,
- Redis.
