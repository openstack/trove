.. _create_db:

=====================================
Create and access a database instance
=====================================
Assume that you have installed the Database service and populated your
data store with images for the type and versions of databases that you
want, and that you can create and access a database instance.

This example shows you how to create and access a MySQL 5.7 database.

Create and access a database instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. **Determine which flavor to use for your database**

   When you create a database instance, you must specify a nova flavor.
   The flavor indicates various characteristics of the instance, such as
   RAM and root volume size. You will need to create or
   obtain new nova flavors that work for databases.

   The first step is to list flavors by using the
   :command:`openstack flavor list` command.

   .. code-block:: console

      $ openstack flavor list

   Now take a look at the minimum requirements for various database
   instances:

   +--------------------+--------------------+--------------------+--------------------+
   | Database           | RAM (MB)           | Disk (GB)          | VCPUs              |
   +====================+====================+====================+====================+
   | MySQL              | 512                | 5                  | 1                  |
   +--------------------+--------------------+--------------------+--------------------+
   | Cassandra          | 2048               | 5                  | 1                  |
   +--------------------+--------------------+--------------------+--------------------+
   | MongoDB            | 1024               | 5                  | 1                  |
   +--------------------+--------------------+--------------------+--------------------+
   | Redis              | 512                | 5                  | 1                  |
   +--------------------+--------------------+--------------------+--------------------+

   -  If you have a custom flavor that meets the needs of the database
      that you want to create, proceed to
      :ref:`Step 2 <create-database-instance>` and use that flavor.

   -  If your environment does not have a suitable flavor, an
      administrative user must create a custom flavor by using the
      :command:`openstack flavor create` command.

   **MySQL example.** This example creates a flavor that you can use
   with a MySQL database. This example has the following attributes:

   -  Flavor name: ``mysql_minimum``

   -  Flavor ID: You must use an ID that is not already in use. In this
      example, IDs 1 through 5 are in use, so use ID ``6``.

   -  RAM: ``512``

   -  Root volume size in GB: ``5``

   -  Virtual CPUs: ``1``

   .. code-block:: console

      $ openstack flavor create mysql-minimum --id 6 --ram 512 --disk 5 --vcpus 1
      +----------------------------+---------------+
      | Field                      | Value         |
      +----------------------------+---------------+
      | OS-FLV-DISABLED:disabled   | False         |
      | OS-FLV-EXT-DATA:ephemeral  | 0             |
      | disk                       | 5             |
      | id                         | 6             |
      | name                       | mysql-minimum |
      | os-flavor-access:is_public | True          |
      | properties                 |               |
      | ram                        | 512           |
      | rxtx_factor                | 1.0           |
      | swap                       |               |
      | vcpus                      | 1             |
      +----------------------------+---------------+

   .. _create-database-instance:

#. **Create a database instance**

   This example creates a database instance with the following
   parameters:

   -  Name of the instance: ``mysql_instance_1``
   -  Database flavor: ``6``
   -  A volume size of ``5`` (5 GB)
   -  A database named ``test``
   -  The database is based on the ``mysql`` data store and the
      ``5.7`` datastore version
   -  The ``userA`` user with the ``password`` password.
   -  A Neutron network ``8799cf10-01ef-40e2-b04e-06da7cfa5668`` to allocate
      the database IP address (for internal access).
   -  Expose the instance to the public via ``--is-public`` (for external
      access). Ignore this parameter if you don't want to expose database
      service to the public internet.
   -  Only the IP addresses coming from ``202.37.199.1/24`` or ``10.1.0.1/24``
      are allowed to access the database service.

   .. code-block:: console

      $ openstack database instance create mysql_instance_1 \
          --flavor 6 \
          --size 5 \
          --nic net-id=8799cf10-01ef-40e2-b04e-06da7cfa5668 \
          --databases test --users userA:password \
          --datastore mysql --datastore-version 5.7 \
          --is-public \
          --allowed-cidr 10.1.0.1/24 \
          --allowed-cidr 202.37.199.1/24
      +-------------------+--------------------------------------+
      | Field             | Value                                |
      +-------------------+--------------------------------------+
      | created           | 2019-09-11T09:19:18                  |
      | datastore         | mysql                                |
      | datastore_version | 5.7                                  |
      | flavor            | 6                                    |
      | id                | 4bca2f27-f986-419e-ab4a-df1db399d590 |
      | name              | mysql_instance_1                     |
      | region            | RegionOne                            |
      | status            | BUILD                                |
      | updated           | 2019-09-11T09:19:18                  |
      | volume            | 5                                    |
      +-------------------+--------------------------------------+

#. **Get the IP address of the database instance**

   Both internal and external IP addresses can be shown by running:

   .. code-block:: console

      $ openstack database instance show 4bca2f27-f986-419e-ab4a-df1db399d590
      +-------------------+--------------------------------------+
      | Field             | Value                                |
      +-------------------+--------------------------------------+
      | created           | 2019-09-11T07:14:37                  |
      | datastore         | mysql                                |
      | datastore_version | 5.7                                  |
      | flavor            | 6                                    |
      | id                | 4bca2f27-f986-419e-ab4a-df1db399d590 |
      | ip                | 10.1.0.14, 172.24.5.15               |
      | name              | mysql_instance_1                     |
      | region            | RegionOne                            |
      | status            | ACTIVE                               |
      | updated           | 2019-09-11T07:14:47                  |
      | volume            | 5                                    |
      | volume_used       | 0.12                                 |
      +-------------------+--------------------------------------+

#. **Access the new database**

   You can now access the new database you just created by using
   typical database access commands. In this MySQL example, replace
   ``IP_ADDRESS`` with either 10.1.0.14 or 172.24.5.15 according to where the
   command is running. Make sure your IP address is in the allowed CIDRs
   specified in the above command.

   .. code-block:: console

      $ mysql -h IP_ADDRESS -uuserA -ppassword
