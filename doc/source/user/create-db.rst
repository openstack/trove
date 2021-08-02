.. _create_db:

=====================================
Create and access a database instance
=====================================
Assume that you have installed the Database service and populated your
data store with images for the type and versions of databases that you
want, and that you can create and access a database instance.

This example shows you how to create and access a MySQL 5.7.29 database.

Create and access a database instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. **Before creating the instance**

   * Choose the flavor. A flavor defines RAM and root volume size for the instance. Trove OpenStack CLI provides a command to get a flavor list that are supported to create trove instance.

      .. code-block:: console

         $ openstack database flavor list

      .. note::

         If creating instance as a replica for the replication cluster, flavor is not needed as it's the same with the replication primary.

   * Choose a neutron network that the instance is allocated IP address from. You can either specify the network ID or the subnet ID, you can even specify the IP address (must be available).
   * Choose the volume size. The cinder volume is used as data storage for the database.
   * Choose datastore version.

      .. note::

         If creating instance as a replica for the replication cluster, datastore is not needed as it's the same with the replication primary.

   * (Optional) Choose the data source. You can create a new instance by restoring a backup using ``--backup <BACKUP_ID>``, or create a replica instance for a replication cluster using ``--replica-of <PRIMARY_INSTANCE_ID>``

#. **Create a database instance**

   This example creates a database instance with the following
   parameters:

   -  Name of the instance: ``mysql_instance_1``
   -  Database flavor: ``1fb05bb0-4605-48b6-81e6-3d4622e4a330``
   -  A volume size of ``5`` (5 GB)
   -  A database named ``test``
   -  The database is based on the ``mysql`` data store and the
      ``5.7.29`` datastore version
   -  The ``userA`` user with the ``password`` password.
   -  A Neutron network ``8799cf10-01ef-40e2-b04e-06da7cfa5668`` to allocate
      the database IP address (for internal access).
   -  Expose the instance to the public via ``--is-public`` (for external
      access).
   -  Only the IP addresses coming from ``202.37.199.1/24`` or ``10.1.0.1/24``
      are allowed to access the database.

   .. code-block:: console

      $ openstack database instance create mysql_instance_1 \
          --flavor 6 \
          --size 5 \
          --nic net-id=8799cf10-01ef-40e2-b04e-06da7cfa5668 \
          --databases test --users userA:password \
          --datastore mysql --datastore-version 5.7.29 \
          --is-public \
          --allowed-cidr 10.1.0.1/24 \
          --allowed-cidr 202.37.199.1/24
      +--------------------------+--------------------------------------+
      | Field                    | Value                                |
      +--------------------------+--------------------------------------+
      | allowed_cidrs            | [10.1.0.1/24, 202.37.199.1/24]       |
      | created                  | 2020-12-08T21:00:19                  |
      | datastore                | mysql                                |
      | datastore_version        | 5.7.29                               |
      | datastore_version_number | 5.7.29                               |
      | flavor                   | 1fb05bb0-4605-48b6-81e6-3d4622e4a330 |
      | id                       | ad40cf6c-6532-4a22-a3f3-7364f0f04a0f |
      | name                     | mysql_instance_1                     |
      | operating_status         |                                      |
      | public                   | True                                 |
      | region                   | RegionOne                            |
      | service_status_updated   | 2020-12-08T21:00:19                  |
      | status                   | BUILD                                |
      | updated                  | 2020-12-08T21:00:19                  |
      | volume                   | 5                                    |
      +--------------------------+--------------------------------------+

#. **Get the IP address of the database instance**

   Wait until the instance ``operating_status`` changes to HEALTHY before getting IP address to access the database:

   .. code-block:: console

      $ openstack database instance show ad40cf6c-6532-4a22-a3f3-7364f0f04a0f
      +--------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
      | Field                    | Value                                                                                                                                           |
      +--------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
      | addresses                | [{'address': '10.0.0.59', 'type': 'private', 'network': '09f6aadc-f92d-41d4-8cad-2eb1876054dd'}, {'address': '172.24.4.242', 'type': 'public'}] |
      | allowed_cidrs            | []                                                                                                                                              |
      | created                  | 2020-12-08T21:00:20                                                                                                                             |
      | datastore                | mysql                                                                                                                                           |
      | datastore_version        | 5.7.29                                                                                                                                          |
      | datastore_version_number | 5.7.29                                                                                                                                          |
      | flavor                   | 1fb05bb0-4605-48b6-81e6-3d4622e4a330                                                                                                            |
      | id                       | ad40cf6c-6532-4a22-a3f3-7364f0f04a0f                                                                                                            |
      | ip                       | 10.0.0.59, 172.24.4.242                                                                                                                         |
      | name                     | mysql_instance_1                                                                                                                                |
      | operating_status         | HEALTHY                                                                                                                                         |
      | public                   | True                                                                                                                                            |
      | region                   | RegionOne                                                                                                                                       |
      | service_status_updated   | 2020-12-08T21:05:51                                                                                                                             |
      | status                   | ACTIVE                                                                                                                                          |
      | updated                  | 2020-12-08T21:04:39                                                                                                                             |
      | volume                   | 5                                                                                                                                               |
      | volume_used              | 0.2                                                                                                                                             |
      +--------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+

#. **Access the new database**

   You can now access the new database you just created by using
   typical database access commands. In this MySQL example, replace
   ``IP_ADDRESS`` with either 10.0.0.59 or 172.24.4.242 according to where the
   command is running. Make sure your IP address is in the allowed CIDRs
   specified in the above command.

   .. code-block:: console

      $ mysql -h IP_ADDRESS -uuserA -ppassword
