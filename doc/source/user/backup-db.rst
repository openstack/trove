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
          +--------------------------------------+--------+-----------+-------------------+--------+-----------+------+
          |                  id                  |  name  | datastore | datastore_version | status | flavor_id | size |
          +--------------------------------------+--------+-----------+-------------------+--------+-----------+------+
          | 97b4b853-80f6-414f-ba6f-c6f455a79ae6 | guest1 |   mysql   |     mysql-5.5     | ACTIVE |     10    |  2   |
          +--------------------------------------+--------+-----------+-------------------+--------+-----------+------+

   2. Optionally, create a backup strategy for the instance. You can also specify a different swift container name (``--swift-container``) when creating the backup.

      .. code-block:: console

          $ openstack database backup strategy create --instance-id 97b4b853-80f6-414f-ba6f-c6f455a79ae6 --swift-container my-trove-backups
          +-----------------+--------------------------------------+
          | Field           | Value                                |
          +-----------------+--------------------------------------+
          | backend         | swift                                |
          | instance_id     | 97b4b853-80f6-414f-ba6f-c6f455a79ae6 |
          | project_id      | 922b47766bcb448f83a760358337f2b4     |
          | swift_container | my-trove-backups                     |
          +-----------------+--------------------------------------+

#. **Backup the database instance**

   Back up the database instance by using the :command:`openstack database backup create`
   command. In this example, the backup is called ``backup1``.

   .. code-block:: console

      $ openstack database backup create 97b4b853-80f6-414f-ba6f-c6f455a79ae6 backup1
      +-------------+--------------------------------------+
      |   Property  |                Value                 |
      +-------------+--------------------------------------+
      |   created   |         2014-03-18T17:09:07          |
      | description |                 None                 |
      |      id     | 8af30763-61fd-4aab-8fe8-57d528911138 |
      | instance_id | 97b4b853-80f6-414f-ba6f-c6f455a79ae6 |
      | locationRef |                 None                 |
      |     name    |               backup1                |
      |  parent_id  |                 None                 |
      |     size    |                 None                 |
      |    status   |                 NEW                  |
      |   updated   |         2014-03-18T17:09:07          |
      +-------------+--------------------------------------+

   Later on, use either :command:`openstack database backup list` command or
   :command:`openstack database backup show` command to check the backup
   status:

   .. code-block:: console

      $ openstack database backup list
      +--------------------------------------+--------------------------------------+---------+-----------+-----------+---------------------+
      |                  id                  |             instance_id              |   name  |   status  | parent_id |       updated       |
      +--------------------------------------+--------------------------------------+---------+-----------+-----------+---------------------+
      | 8af30763-61fd-4aab-8fe8-57d528911138 | 97b4b853-80f6-414f-ba6f-c6f455a79ae6 | backup1 | COMPLETED |    None   | 2014-03-18T17:09:11 |
      +--------------------------------------+--------------------------------------+---------+-----------+-----------+---------------------+
      $ openstack database backup show 8af30763-61fd-4aab-8fe8-57d528911138
      +-------------+----------------------------------------------------+
      |   Property  |                   Value                            |
      +-------------+----------------------------------------------------+
      |   created   |              2014-03-18T17:09:07                   |
      | description |                   None                             |
      |      id     |                 8af...138                          |
      | instance_id |                 97b...ae6                          |
      | locationRef | http://10.0.0.1:.../.../8af...138.xbstream.gz.enc  |
      |     name    |                 backup1                            |
      |  parent_id  |                  None                              |
      |     size    |                  0.17                              |
      |    status   |               COMPLETED                            |
      |   updated   |           2014-03-18T17:09:11                      |
      +-------------+----------------------------------------------------+

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
      | 8af30763-61fd-4aab-8fe8-57d528911138.xbstream.gz |
      +--------------------------------------------------+

#. **Restore a database instance**

   Now assume that the ``guest1`` database instance is damaged and you
   need to restore it. In this example, you use the :command:`openstack database instance create`
   command to create a new database instance called ``guest2``.

   -  Specify that the new ``guest2`` instance has the same flavor
      (``10``) and the same root volume size (``2``) as the original
      ``guest1`` instance.

   -  Use the ``--backup`` argument to indicate that this new
      instance is based on the backup artifact identified by
      ``BACKUP_ID``. In this example, replace ``BACKUP_ID`` with
      ``8af30763-61fd-4aab-8fe8-57d528911138``.

   .. code-block:: console

      $ openstack database instance create guest2 --flavor 10 --size 2 --nic net-id=$network_id --backup BACKUP_ID
      +-------------------+----------------------------------------------+
      |      Property     |                Value                         |
      +-------------------+----------------------------------------------+
      |      created      |         2014-03-18T17:12:03                  |
      |     datastore     | {u'version': u'mysql-5.5', u'type': u'mysql'}|
      |datastore_version  |                mysql-5.5                     |
      |       flavor      | {u'id': u'10', u'links': [{u'href': ...]}    |
      |         id        |  ac7a2b35-a9b4-4ff6-beac-a1bcee86d04b        |
      |        name       |                guest2                        |
      |       status      |                 BUILD                        |
      |      updated      |          2014-03-18T17:12:03                 |
      |       volume      |             {u'size': 2}                     |
      +-------------------+----------------------------------------------+

#. **Verify backup**

   Now check that the new ``guest2`` instance has the same
   characteristics as the original ``guest1`` instance.

   Start by getting the ID of the new ``guest2`` instance.

   .. code-block:: console

      $ openstack database instance list

      +-----------+--------+-----------+-------------------+--------+-----------+------+
      |     id    |  name  | datastore | datastore_version | status | flavor_id | size |
      +-----------+--------+-----------+-------------------+--------+-----------+------+
      | 97b...ae6 | guest1 |   mysql   |     mysql-5.5     | ACTIVE |     10    |  2   |
      | ac7...04b | guest2 |   mysql   |     mysql-5.5     | ACTIVE |     10    |  2   |
      +-----------+--------+-----------+-------------------+--------+-----------+------+

   Use the :command:`openstack database instance show` command to display information about the new
   guest2 instance. Pass in guest2's ``INSTANCE_ID``, which is
   ``ac7a2b35-a9b4-4ff6-beac-a1bcee86d04b``.

   .. code-block:: console

      $ openstack database instance show INSTANCE_ID
      +-------------------+--------------------------------------+
      |      Property     |                Value                 |
      +-------------------+--------------------------------------+
      |      created      |         2014-03-18T17:12:03          |
      |     datastore     |                mysql                 |
      | datastore_version |              mysql-5.5               |
      |       flavor      |                  10                  |
      |         id        | ac7a2b35-a9b4-4ff6-beac-a1bcee86d04b |
      |         ip        |               10.0.0.3               |
      |        name       |                guest2                |
      |       status      |                ACTIVE                |
      |      updated      |         2014-03-18T17:12:06          |
      |       volume      |                  2                   |
      |    volume_used    |                 0.18                 |
      +-------------------+--------------------------------------+

   Note that the data store, flavor ID, and volume size have the same
   values as in the original ``guest1`` instance.

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

   Tell the users who were accessing the now-disabled ``guest1``
   database instance that they can now access ``guest2``. Provide them
   with ``guest2``'s name, IP address, and any other information they
   might need. (You can get this information by using the
   :command:`openstack database instance show` command.)

#. **Clean up**

   At this point, you might want to delete the disabled ``guest1``
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

    $ openstack database backup create INSTANCE_ID backup1.1  --parent BACKUP_ID
    +-------------+--------------------------------------+
    |   Property  |                Value                 |
    +-------------+--------------------------------------+
    |   created   |         2014-03-19T14:09:13          |
    | description |                 None                 |
    |      id     | 1d474981-a006-4f62-b25f-43d7b8a7097e |
    | instance_id | 792a6a56-278f-4a01-9997-d997fa126370 |
    | locationRef |                 None                 |
    |     name    |              backup1.1               |
    |  parent_id  | 6dc3a9b7-1f3e-4954-8582-3f2e4942cddd |
    |     size    |                 None                 |
    |    status   |                 NEW                  |
    |   updated   |         2014-03-19T14:09:13          |
    +-------------+--------------------------------------+

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
