=============================
Backup and restore a database
=============================

You can use Database services to backup a database and store the backup
artifact in the Object Storage service. Later on, if the original database is
damaged, you can use the backup artifact to restore the database. The restore
process creates a new database instance.

The backup data is stored in OpenStack Swift, the user is able to customize
which container to store the data. The following ways are described in the
order of precedence from greatest to least:

1. The container name can be specified when creating backups, this could
   override either the backup strategy setting or the default setting in Trove
   configuration.

2. Users could create backup strategy either for the project scope or for a
   particular instance.

3. If not configured by the end user, will use the default value in Trove
   configuration.

.. caution::

    If the objects in the backup container are manually deleted, the
    database can't be properly restored.

This example shows you how to create backup strategy, create backup and restore
instance from the backup.

#. **Before creating backup**

   1. Make sure you have created an instance, e.g. in this example, we use the following instance:

      .. code-block:: console

          $ openstack database instance list
          +--------------------------------------+--------+-----------+-------------------+--------+------------------+--------+-------------------------------------------------------------------------------------------------+-----------+------+------+
          | ID                                   | Name   | Datastore | Datastore Version | Status | Operating Status | Public | Addresses                                                                                       | Flavor ID | Size | Role |
          +--------------------------------------+--------+-----------+-------------------+--------+------------------+--------+-------------------------------------------------------------------------------------------------+-----------+------+------+
          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f | mysql1 | mysql     | 8.0.29            | ACTIVE | HEALTHY          | False  | [{'address': '10.0.0.9', 'type': 'private', 'network': '33f3a589-b806-4212-9a59-8e058cac0699'}] | d2        |    1 |      |
          +--------------------------------------+--------+-----------+-------------------+--------+------------------+--------+-------------------------------------------------------------------------------------------------+-----------+------+------+

   2. Optionally, create a backup strategy for the instance. You can also specify a different swift container name (``--swift-container``) when creating the backup.

      .. code-block:: console

          $ openstack database backup strategy create --instance-id 78e338e3-d1c4-4189-8ea7-bfc1fab5011f --swift-container my-trove-backups
          +-----------------+--------------------------------------+
          | Field           | Value                                |
          +-----------------+--------------------------------------+
          | backend         | swift                                |
          | instance_id     | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f |
          | project_id      | fc51186c63df417ea63cec6c65a2d564     |
          | swift_container | my-trove-backups                     |
          +-----------------+--------------------------------------+

#. **Backup the database instance**

   Back up the database instance by using the :command:`openstack database backup create`
   command. In this example, the backup is called ``mysql-backup-name1``.

   .. code-block:: console

      $ openstack database backup create mysql-backup-name1 --instance mysql1 --swift-container 'my-trove-backups'
      +----------------------+--------------------------------------+
      | Field                | Value                                |
      +----------------------+--------------------------------------+
      | created              | 2022-10-24T01:46:38                  |
      | datastore            | mysql                                |
      | datastore_version    | 8.0.29                               |
      | datastore_version_id | 324f2bdf-6099-4754-a5f9-82abee026a19 |
      | description          | None                                 |
      | id                   | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43 |
      | instance_id          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f |
      | locationRef          | None                                 |
      | name                 | mysql-backup-name1                   |
      | parent_id            | None                                 |
      | project_id           | fc51186c63df417ea63cec6c65a2d564     |
      | size                 | None                                 |
      | status               | NEW                                  |
      | updated              | 2022-10-24T01:46:38                  |
      +----------------------+--------------------------------------+

   Later on, use either :command:`openstack database backup list` command or
   :command:`openstack database backup show` command to check the backup
   status:

   .. code-block:: console

      $ openstack database backup list
      +--------------------------------------+--------------------------------------+------------------------------+-----------+--------------------------------------+---------------------+----------------------------------+
      | ID                                   | Instance ID                          | Name                         | Status    | Parent ID                            | Updated             | Project ID                       |
      +--------------------------------------+--------------------------------------+------------------------------+-----------+--------------------------------------+---------------------+----------------------------------+
      | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43 | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f | mysql-backup-name1           | COMPLETED | None                                 | 2022-10-24T01:46:55 | fc51186c63df417ea63cec6c65a2d564 |
      +--------------------------------------+--------------------------------------+------------------------------+-----------+--------------------------------------+---------------------+----------------------------------+
      $ openstack database backup show 1ecd0a75-e4aa-400b-b0c8-cb738944fd43
      +----------------------+---------------------------------------------------------------------------------+
      | Field                | Value                                                                           |
      +----------------------+---------------------------------------------------------------------------------+
      | created              | 2022-10-24T01:46:38                                                             |
      | datastore            | mysql                                                                           |
      | datastore_version    | 8.0.29                                                                          |
      | datastore_version_id | 324f2bdf-6099-4754-a5f9-82abee026a19                                            |
      | description          | None                                                                            |
      | id                   | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43                                            |
      | instance_id          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f                                            |
      | locationRef          | http://172.../my-trove-backups/1ecd0a75-e4aa-400b-b0c8-cb738944fd43.xbstream.gz |
      | name                 | mysql-backup-name1                                                              |
      | parent_id            | None                                                                            |
      | project_id           | fc51186c63df417ea63cec6c65a2d564                                                |
      | size                 | 0.19                                                                            |
      | status               | COMPLETED                                                                       |
      | updated              | 2022-10-24T01:46:55                                                             |
      +----------------------+---------------------------------------------------------------------------------+

#. **Check the backup data in Swift**

   Check the container is created and the backup data is saved as objects inside the container.

   .. code-block:: console

      $ openstack container list
      +------------------+
      | Name             |
      +------------------+
      | my-trove-backups |
      +------------------+
      $ openstack object list my-trove-backups
      +--------------------------------------------------+
      | Name                                             |
      +--------------------------------------------------+
      | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43.xbstream.gz |
      +--------------------------------------------------+

#. **Restore a database instance**

   Now assume that the ``mysql1`` database instance is damaged and you
   need to restore it. In this example, you use the :command:`openstack database instance create`
   command to create a new database instance called ``mysql2``.

   -  Specify that the new ``mysql2`` instance has the same flavor
      (``d2``) and the same root volume size (``1``) as the original
      ``mysql1`` instance.

   -  Use the ``--backup`` argument to indicate that this new
      instance is based on the backup artifact identified by
      the ID of ``mysql-backup-name1``.

   .. code-block:: console

      $ openstack database instance create mysql2 --flavor d2 --nic net-id=$network_id
            --datastore mysql --datastore-version 8.0.29 --datastore-version-number 8.0.29 --size 1 \
            --backup $(openstack database backup show mysql-backup-name1 -f value -c id)
      +--------------------------+--------------------------------------+
      | Field                    | Value                                |
      +--------------------------+--------------------------------------+
      | allowed_cidrs            | []                                   |
      | created                  | 2022-10-24T01:56:55                  |
      | datastore                | mysql                                |
      | datastore_version        | 8.0.29                               |
      | datastore_version_number | 8.0.29                               |
      | encrypted_rpc_messaging  | True                                 |
      | flavor                   | d2                                   |
      | id                       | 62f0f152-8cd5-42b3-9cd6-91bda651a4c0 |
      | name                     | mysql2                               |
      | operating_status         |                                      |
      | public                   | False                                |
      | region                   | RegionOne                            |
      | server_id                | None                                 |
      | service_status_updated   | 2022-10-24T01:56:55                  |
      | status                   | BUILD                                |
      | tenant_id                | fc51186c63df417ea63cec6c65a2d564     |
      | updated                  | 2022-10-24T01:56:55                  |
      | volume                   | 1                                    |
      | volume_id                | None                                 |
      +--------------------------+--------------------------------------+

#. **Verify backup**

   Now check that the new ``mysql2`` instance has the same
   characteristics as the original ``mysql1`` instance.

   Start by getting the ID of the new ``mysql2`` instance.

   .. code-block:: console

      $ openstack database instance list
      +--------------------------------------+--------+-----------+-------------------+--------+------------------+--------+--------------------------------------------------------------------------------------------------+-----------+------+------+
      | ID                                   | Name   | Datastore | Datastore Version | Status | Operating Status | Public | Addresses                                                                                        | Flavor ID | Size | Role |
      +--------------------------------------+--------+-----------+-------------------+--------+------------------+--------+--------------------------------------------------------------------------------------------------+-----------+------+------+
      | 6eef378d-1d9c-4e48-b206-b3db130d750d | mysql2 | mysql     | 8.0.29            | ACTIVE | HEALTHY          | False  | [{'address': '10.0.0.8', 'type': 'private', 'network': '33f3a589-b806-4212-9a59-8e058cac0699'}]  | d2        |    1 |      |
      | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f | mysql1 | mysql     | 8.0.29            | ACTIVE | HEALTHY          | False  | [{'address': '10.0.0.18', 'type': 'private', 'network': '33f3a589-b806-4212-9a59-8e058cac0699'}] | d2        |    1 |      |
      +--------------------------------------+--------+-----------+-------------------+--------+------------------+--------+--------------------------------------------------------------------------------------------------+-----------+------+------+

   Use the :command:`openstack database instance show` command to display information about the new
   mysql2 instance. Pass in mysql2's ``INSTANCE_ID``, which is
   ``6eef378d-1d9c-4e48-b206-b3db130d750d``.

   .. code-block:: console

      $ openstack database instance show mysql2
      +--------------------------+-------------------------------------------------------------------------------------------------+
      | Field                    | Value                                                                                           |
      +--------------------------+-------------------------------------------------------------------------------------------------+
      | addresses                | [{'address': '10.0.0.8', 'type': 'private', 'network': '33f3a589-b806-4212-9a59-8e058cac0699'}] |
      | allowed_cidrs            | []                                                                                              |
      | created                  | 2022-10-24T01:58:51                                                                             |
      | datastore                | mysql                                                                                           |
      | datastore_version        | 8.0.29                                                                                          |
      | datastore_version_number | 8.0.29                                                                                          |
      | encrypted_rpc_messaging  | True                                                                                            |
      | flavor                   | d2                                                                                              |
      | id                       | 6eef378d-1d9c-4e48-b206-b3db130d750d                                                            |
      | ip                       | 10.0.0.8                                                                                        |
      | name                     | mysql2                                                                                          |
      | operating_status         | HEALTHY                                                                                         |
      | public                   | False                                                                                           |
      | region                   | RegionOne                                                                                       |
      | server_id                | 7a8cd089-bd1c-4230-aedd-ced4e945ad46                                                            |
      | service_status_updated   | 2022-10-24T02:12:35                                                                             |
      | status                   | ACTIVE                                                                                          |
      | tenant_id                | fc51186c63df417ea63cec6c65a2d564                                                                |
      | updated                  | 2022-10-24T02:05:03                                                                             |
      | volume                   | 1                                                                                               |
      | volume_id                | 7080954f-e22f-4442-8f40-e26aaa080c9d                                                            |
      | volume_used              | 0.19                                                                                            |
      +--------------------------+-------------------------------------------------------------------------------------------------+

   Note that the data store, flavor ID, and volume size have the same
   values as in the original ``mysql1`` instance.

   Use the :command:`openstack database db list` command to check that the original
   databases (``db1`` and ``db2``) are present on the restored instance.

   .. code-block:: console

      $ openstack database db list INSTANCE_ID
      +--------------------+
      |        name        |
      +--------------------+
      |        db1         |
      |        db2         |
      | performance_schema |
      |        test        |
      +--------------------+

   Use the :command:`openstack database user list` command to check that the original user
   (``user1``) is present on the restored instance.

   .. code-block:: console

      $ openstack database user list INSTANCE_ID
      +--------+------+-----------+
      |  name  | host | databases |
      +--------+------+-----------+
      | user1  |  %   |  db1, db2 |
      +--------+------+-----------+

#. **Notify users**

   Tell the users who were accessing the now-disabled ``mysql1``
   database instance that they can now access ``mysql2``. Provide them
   with ``mysql2``'s name, IP address, and any other information they
   might need. (You can get this information by using the
   :command:`openstack database instance show` command.)

#. **Clean up**

   At this point, you might want to delete the disabled ``mysql1``
   instance, by using the :command:`openstack database instance delete` command.

   .. code-block:: console

      $ openstack database instance delete INSTANCE_ID

Create incremental backups
--------------------------

Incremental backups let you chain together a series of backups. You start with
a regular backup. Then, when you want to create a subsequent incremental
backup, you specify the parent backup.

Restoring a database instance from an incremental backup is the same as
creating a database instance from a regular backup. the Database service
handles the process of applying the chain of incremental backups.

Create an incremental backup based on a parent backup:

.. code-block:: console

    $ openstack database backup create mysql-backup-name1.1 --instance mysql1 --swift-container 'my-trove-backups' \
          --parent $(openstack database backup show mysql-backup-name1 -f value -c id)
    +----------------------+--------------------------------------+
    | Field                | Value                                |
    +----------------------+--------------------------------------+
    | created              | 2022-10-24T02:38:41                  |
    | datastore            | mysql                                |
    | datastore_version    | 8.0.29                               |
    | datastore_version_id | 324f2bdf-6099-4754-a5f9-82abee026a19 |
    | description          | None                                 |
    | id                   | e15ae06a-3afb-4794-8890-7059317b2218 |
    | instance_id          | 78e338e3-d1c4-4189-8ea7-bfc1fab5011f |
    | locationRef          | None                                 |
    | name                 | mysql-backup-name1.1                 |
    | parent_id            | 1ecd0a75-e4aa-400b-b0c8-cb738944fd43 |
    | project_id           | fc51186c63df417ea63cec6c65a2d564     |
    | size                 | None                                 |
    | status               | NEW                                  |
    | updated              | 2022-10-24T02:38:41                  |
    +----------------------+--------------------------------------+

Restore backup from other regions
---------------------------------

The feature of restoring backup from other regions was introduced in Wallaby.

In multi-region deployment with geo-replicated Swift, the user is able to
create a backup in one region using the backup data created in the others,
which is useful in Disaster Recovery scenario. Instance ID is not required in
this case when restoring backup, but the original backup data location (a swift
object URL), the local datastore version and the backup data size are required.

.. warning::

   The restored backup is dependent on the original backup data, if the
   original backup is deleted, the restored backup is invalid.

#. In region 1, get the backup information.

   .. code-block:: console

      $ openstack database backup show b3957063-18ac-48f4-a710-82602f2ddb78 -c locationRef -c size -c datastore -c datastore_version
      +-------------------+---------------------------------------------------------------------------------------------------------------------------------------+
      | Field             | Value                                                                                                                                 |
      +-------------------+---------------------------------------------------------------------------------------------------------------------------------------+
      | datastore         | mysql                                                                                                                                 |
      | datastore_version | 5.7.29                                                                                                                                |
      | locationRef       | http://192.168.206.8:8080/v1/AUTH_055b2fb9a2264ae5a5f6b3cc066c4a1d/trove-backup-data/b3957063-18ac-48f4-a710-82602f2ddb78.xbstream.gz |
      | size              | 0.2                                                                                                                                   |
      +-------------------+---------------------------------------------------------------------------------------------------------------------------------------+

#. In region 2, create a new backup.

   .. code-block:: console

      $ openstack database backup create \
        --restore-from http://192.168.206.8:8080/v1/AUTH_055b2fb9a2264ae5a5f6b3cc066c4a1d/trove-backup-data/b3957063-18ac-48f4-a710-82602f2ddb78.xbstream.gz \
        --restore-datastore-version 40430eea-9ee3-4c2c-a06f-9ec72277af7a \
        --restore-size 0.3 test-restore
      +----------------------+---------------------------------------------------------------------------------------------------------------------------------------+
      | Field                | Value                                                                                                                                 |
      +----------------------+---------------------------------------------------------------------------------------------------------------------------------------+
      | created              | 2021-02-22T01:44:06                                                                                                                   |
      | datastore            | mysql                                                                                                                                 |
      | datastore_version    | 5.7.29                                                                                                                                |
      | datastore_version_id | 40430eea-9ee3-4c2c-a06f-9ec72277af7a                                                                                                  |
      | description          | None                                                                                                                                  |
      | id                   | ad98bbb0-b1d8-4569-b404-7e6af6700235                                                                                                  |
      | instance_id          | None                                                                                                                                  |
      | locationRef          | http://192.168.206.8:8080/v1/AUTH_055b2fb9a2264ae5a5f6b3cc066c4a1d/trove-backup-data/b3957063-18ac-48f4-a710-82602f2ddb78.xbstream.gz |
      | name                 | test-restore                                                                                                                          |
      | parent_id            | None                                                                                                                                  |
      | project_id           | 055b2fb9a2264ae5a5f6b3cc066c4a1d                                                                                                      |
      | size                 | 0.3                                                                                                                                   |
      | status               | RESTORED                                                                                                                              |
      | updated              | 2021-02-22T01:44:06                                                                                                                   |
      +----------------------+---------------------------------------------------------------------------------------------------------------------------------------+

Troubleshooting
---------------

Failed to create incremental backup for PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

One possible reason could be it has been a long time since the parent backup was created, and the parent backup WAL file is removed internally because of disk pressure, it could be confirmed by checking the instance detail, e.g.

.. code-block:: console

   $ openstack database instance show e7231e46-ca3b-4dce-bf67-739b3af0ef85 -c fault
   +-------+----------------------------------------------------------------------+
   | Field | Value                                                                |
   +-------+----------------------------------------------------------------------+
   | fault | Failed to create backup c76de467-6587-4e27-bb8d-7c3d3b136663, error: |
   |       |     Cannot find parent backup WAL file.                              |
   +-------+----------------------------------------------------------------------+

In this case, you have to create full backup instead.

To avoid this issue in the future, you can set up a cron job to create (incremental) backups regularly.
