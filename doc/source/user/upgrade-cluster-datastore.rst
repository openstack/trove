=========================
Upgrade cluster datastore
=========================

.. caution::

   Database clustering function is still in experimental, should not be used
   in production environment.

Upgrading datastore for cluster instances is very similar to upgrading
a single instance.

Trove tries to perform a rolling upgrade so that there won't be any
downtime. However, it is not always possible and, for example, in case
of Redis upgrade, some of its slots may be temporarily unavailable.

Trove strategy upgrades every instance in the entire cluster one by
one. Upgrading is finished once all instances are upgraded.

Please check the guide for datastore upgrade to check prerequisistes.

This example shows you how to upgrade Redis datastore (version 3.2.6)
for a cluster.

Upgrading cluster
~~~~~~~~~~~~~~~~~

#. **Check cluster task**

   Use :command:`openstack database cluster list` to check whether the
   task of your cluster is NONE.

   .. code-block:: console

       $ openstack database cluster list
       +--------------------------------------+---------------+-----------+-------------------+-----------+
       | ID                                   | Name          | Datastore | Datastore Version | Task Name |
       +--------------------------------------+---------------+-----------+-------------------+-----------+
       | 05f2e7b7-8dac-453f-ad5d-38195cd5718f | redis_cluster | redis     | 3.2.6             | NONE      |
       +--------------------------------------+---------------+-----------+-------------------+-----------+

#. **Check if target version is available**

   Use :command:`openstack datastore version list` to list all
   available versions your datastore.

   .. code-block:: console

       $ openstack datastore version list redis
       +--------------------------------------+-------+
       | ID                                   | Name  |
       +--------------------------------------+-------+
       | 483debec-b7c3-4167-ab1d-1765795ed7eb | 3.2.6 |
       | 507f666e-193c-4194-9d9d-da8342dcb4f1 | 3.2.7 |
       +--------------------------------------+-------+

#. **Run cluster-upgrade**

   Use :command:`openstack database cluster upgrade` command to
   upgrade your datastore for the selected instance.

   .. code-block:: console

      $ openstack database cluster upgrade 05f2e7b7-8dac-453f-ad5d-38195cd5718f 3.2.7

#. **Wait until task changes from UPGRADING_CLUSTER to NONE**

   You can use :command:`openstack database cluster list` to check the
   current task.

   .. code-block:: console

       $ openstack database cluster list
       +--------------------------------------+---------------+-----------+-------------------+-----------+
       | ID                                   | Name          | Datastore | Datastore Version | Task Name |
       +--------------------------------------+---------------+-----------+-------------------+-----------+
       | 05f2e7b7-8dac-453f-ad5d-38195cd5718f | redis_cluster | redis     | 3.2.7             | NONE      |
       +--------------------------------------+---------------+-----------+-------------------+-----------+

Other clusters
~~~~~~~~~~~~~~~

Upgrade for other clusters works in the same way. Currently Trove
supports upgrades for the following cluster datastores:

- MySQL.
- MariaDB.
- Redis.
