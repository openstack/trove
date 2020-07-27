===========================
Set up database replication
===========================

You can create replicas of an existing database instance(the primary) to
improve the performance and scale of read-intensive workloads. Read workloads
can be isolated to the replicas, while write workloads can be directed to the
primary. When you make subsequent changes to the primary, the system
automatically applies those changes to the replicas. Because replicas are
read-only, they don't directly reduce write-capacity burdens on the primary.
This feature isn't targeted at write-intensive workloads.

- Not all the datastores support replication feature in Trove.

- A replica is created by using the same server configuration as the primary,
  e.g. flavor, data volume, datastore, etc. After a replica is created, several
  settings can be changed independently from the primary server, e.g. the data
  volume size.

- Currently, There is no automated failover between primary and replicas.

- Trove can only create a new replica. Adding an already existing instance to
  the replication group is not supported.

- Creating a replica of a replica is not supported.

- When deleting replication instances, replicas need to be removed before the
  primary.

Set up replication
------------------

#. Create a replica

   First, make sure you have an instance (ID:
   cebbf187-e223-46dd-8802-6dc04e895d0a) up and running in HEALTHY status,
   create a replica:

   .. code-block:: console

      $ openstack database instance create test-mysql-replica-1 \
          --nic net-id=$netid \
          --replica_of cebbf187-e223-46dd-8802-6dc04e895d0a

#. Wait for the replica instance successfully created, verify status of the
   replication servers.

   .. code-block:: console

      $ odbi list
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+
      | ID                                   | Name                 | Datastore | Datastore Version | Status  | Addresses                                      | Flavor ID | Size | Region    | Role    |
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+
      | 71f30a72-4e47-4505-9e7f-ffd8933a331c | test-mysql-replica-1 | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.155', 'type': 'private'}] | d2        |    2 | RegionOne | replica |
      | cebbf187-e223-46dd-8802-6dc04e895d0a | test-mysql           | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.43', 'type': 'private'}]  | d2        |    2 | RegionOne | primary |
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+

#. Verify replication status.

   Replication can be verified by making some modifications to the primary and
   ensuring that the modifications also propagate back to the replica. We will
   create a database called "newdb" on the primary and check it's automatically
   created on the replica.

   First, get the existing databases of primary and replica, they should be the
   same:

   .. code-block:: console

      $ openstack database db list cebbf187-e223-46dd-8802-6dc04e895d0a # The primary
      +--------+
      | Name   |
      +--------+
      | testdb |
      +--------+
      $ openstack database db list 71f30a72-4e47-4505-9e7f-ffd8933a331c # The replica
      +--------+
      | Name   |
      +--------+
      | testdb |
      +--------+

   Create a new database on the primary:

   .. code-block:: console

      $ openstack database db create cebbf187-e223-46dd-8802-6dc04e895d0a newdb

   Check the new database is also created on the replica:

   .. code-block:: console

      $ openstack database db list 71f30a72-4e47-4505-9e7f-ffd8933a331c
      +--------+
      | Name   |
      +--------+
      | newdb  |
      | testdb |
      +--------+

Failover
--------

Since replication is asynchronous, there is lag between the primary and the
replica. The amount of lag can be influenced by a number of factors like how
heavy the workload running on the primary server is and the latency between
data centers. In most cases, replica lag ranges between a few seconds to a
couple minutes.

#. Before performing failover, we will create one more replica:

   .. code-block:: console

      $ openstack database instance create test-mysql-replica-2 \
          --nic net-id=$netid \
          --replica_of cebbf187-e223-46dd-8802-6dc04e895d0a

   Now we have 3 instances running in a replication group:

   .. code-block:: console

      $ odbi list
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+
      | ID                                   | Name                 | Datastore | Datastore Version | Status  | Addresses                                      | Flavor ID | Size | Region    | Role    |
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+
      | 71f30a72-4e47-4505-9e7f-ffd8933a331c | test-mysql-replica-1 | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.155', 'type': 'private'}] | d2        |    2 | RegionOne | replica |
      | a85ece86-9f62-4aa8-bb15-eba604cd2a01 | test-mysql-replica-2 | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.243', 'type': 'private'}] | d2        |    2 | RegionOne | replica |
      | cebbf187-e223-46dd-8802-6dc04e895d0a | test-mysql           | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.43', 'type': 'private'}]  | d2        |    2 | RegionOne | primary |
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+

#. Failover(promote) "test-mysql-replica-1" to primary.

   .. code-block:: console

      $ openstack database instance promote 71f30a72-4e47-4505-9e7f-ffd8933a331c

   Wait for Trove setting up the new replication, the status of the 3 instances become "PROMOTE" then "HEALTHY".

   .. code-block:: console

      $ openstack database instance list
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+
      | ID                                   | Name                 | Datastore | Datastore Version | Status  | Addresses                                      | Flavor ID | Size | Region    | Role    |
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+
      | 71f30a72-4e47-4505-9e7f-ffd8933a331c | test-mysql-replica-1 | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.155', 'type': 'private'}] | d2        |    2 | RegionOne | primary |
      | a85ece86-9f62-4aa8-bb15-eba604cd2a01 | test-mysql-replica-2 | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.243', 'type': 'private'}] | d2        |    2 | RegionOne | replica |
      | cebbf187-e223-46dd-8802-6dc04e895d0a | test-mysql           | mysql     | 5.7.29            | HEALTHY | [{'address': '10.1.0.43', 'type': 'private'}]  | d2        |    2 | RegionOne | replica |
      +--------------------------------------+----------------------+-----------+-------------------+---------+------------------------------------------------+-----------+------+-----------+---------+

#. Point your application to the (former) replica.

   Each server has a unique connection string. Update your application to point
   to the (former) replica instead of the primary.

Other supported operations
--------------------------

* Remove a failed primary. This essentially is used to eject an already failed
  primary in order to establish a new one between the replicas. Command:
  ``openstack database instance eject <primary_ID>``

* Change replica to a standalone database server. The detached replica becomes
  a standalone server that accepts both reads and writes. The standalone server
  can't be made into a replica again.. Command:
  ``openstack database instance detach <replica_ID>``