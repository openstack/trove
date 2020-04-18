.. _secure_rpc_messaging:

======================
 Secure RPC messaging
======================

Background
----------

Trove uses oslo_messaging.rpc for communication amongst the various
control plane components and the guest agents. For secure operation of
the system, these RPC calls can be fully encrypted. A control plane
encryption key is used for communications between the API service and
the taskmanager, and system generated per-instance keys are used for
communication between the control plane and guest instances.

This document provides some useful tips on how to use this mechanism.

The default system behavior
---------------------------

By default, the system will attempt to encrypt all RPC
communication. This behavior is controlled by the following
configuration parameters:

- enable_secure_rpc_messaging

  boolean that determines whether rpc messages will be secured by
  encryption. The default value is True.

- taskmanager_rpc_encr_key

  the key used for encrypting messages sent to the taskmanager. A
  default value is provided for this and it is important that
  deployers change this.

- inst_rpc_key_encr_key

  the key used for encrypting the per-instance keys when they are
  stored in the trove infrastructure database (catalog). A default is
  provided for this and it is important that deployers change this.


Interoperability and Upgrade
----------------------------

Consider the system as shown below which runs a version of code prior
to the introduciton of this oslo_messaging.rpc security. Observe, for
example that the instances table in the system catalog does not
include the per-instance encrypted key column::

     mysql> describe instances;
     +----------------------+--------------+------+-----+---------+-------+
     | Field                | Type         | Null | Key | Default | Extra |
     +----------------------+--------------+------+-----+---------+-------+
     | id                   | varchar(36)  | NO   | PRI | NULL    |       |
     | created              | datetime     | YES  |     | NULL    |       |
     | updated              | datetime     | YES  |     | NULL    |       |
     | name                 | varchar(255) | YES  |     | NULL    |       |
     | hostname             | varchar(255) | YES  |     | NULL    |       |
     | compute_instance_id  | varchar(36)  | YES  |     | NULL    |       |
     | task_id              | int(11)      | YES  |     | NULL    |       |
     | task_description     | varchar(255) | YES  |     | NULL    |       |
     | task_start_time      | datetime     | YES  |     | NULL    |       |
     | volume_id            | varchar(36)  | YES  |     | NULL    |       |
     | flavor_id            | varchar(255) | YES  |     | NULL    |       |
     | volume_size          | int(11)      | YES  |     | NULL    |       |
     | tenant_id            | varchar(36)  | YES  | MUL | NULL    |       |
     | server_status        | varchar(64)  | YES  |     | NULL    |       |
     | deleted              | tinyint(1)   | YES  | MUL | NULL    |       |
     | deleted_at           | datetime     | YES  |     | NULL    |       |
     | datastore_version_id | varchar(36)  | NO   | MUL | NULL    |       |
     | configuration_id     | varchar(36)  | YES  | MUL | NULL    |       |
     | slave_of_id          | varchar(36)  | YES  | MUL | NULL    |       |
     | cluster_id           | varchar(36)  | YES  | MUL | NULL    |       |
     | shard_id             | varchar(36)  | YES  |     | NULL    |       |
     | type                 | varchar(64)  | YES  |     | NULL    |       |
     | region_id            | varchar(255) | YES  |     | NULL    |       |
     +----------------------+--------------+------+-----+---------+-------+
     23 rows in set (0.00 sec)

We launch an instance of MySQL using this version of the software::

    amrith@amrith-work:/opt/stack/trove/integration/scripts$ openstack network list
    +--------------------------------------+-------------+--------------------------------------+
    | ID                                   | Name        | Subnets                              |
    +--------------------------------------+-------------+--------------------------------------+
    [...]
    | 4bab02e7-87bb-4cc0-8c07-2f282c777c85 | public      | e620c4f5-749c-4212-b1d1-4a6e2c0a3f16 |
    [...]
    +--------------------------------------+-------------+--------------------------------------+

    amrith@amrith-work:/opt/stack/trove/integration/scripts$ trove create m2 25 --size 3 --nic net-id=4bab02e7-87bb-4cc0-8c07-2f282c777c85
    +-------------------+--------------------------------------+
    | Property          | Value                                |
    +-------------------+--------------------------------------+
    | created           | 2017-01-09T18:17:13                  |
    | datastore         | mysql                                |
    | datastore_version | 5.6                                  |
    | flavor            | 25                                   |
    | id                | bb0c9213-31f8-4427-8898-c644254b3642 |
    | name              | m2                                   |
    | region            | RegionOne                            |
    | server_id         | None                                 |
    | status            | BUILD                                |
    | updated           | 2017-01-09T18:17:13                  |
    | volume            | 3                                    |
    | volume_id         | None                                 |
    +-------------------+--------------------------------------+

    amrith@amrith-work:/opt/stack/trove/integration/scripts$ nova list
    +--------------------------------------+------+--------+------------+-------------+-------------------+
    | ID                                   | Name | Status | Task State | Power State | Networks          |
    +--------------------------------------+------+--------+------------+-------------+-------------------+
    | a4769ce2-4e22-4134-b958-6db6c23cb221 | m2   | BUILD  | spawning   | NOSTATE     | public=172.24.4.4 |
    +--------------------------------------+------+--------+------------+-------------+-------------------+

And on that machine, the configuration file looks like this::

    amrith@m2:~$ cat /etc/trove/conf.d/guest_info.conf
    [DEFAULT]
    guest_id=bb0c9213-31f8-4427-8898-c644254b3642
    datastore_manager=mysql
    tenant_id=56cca8484d3e48869126ada4f355c284

The instance goes online::

    amrith@amrith-work:/opt/stack/trove/integration/scripts$ trove show m2
    +-------------------+--------------------------------------+
    | Property          | Value                                |
    +-------------------+--------------------------------------+
    | created           | 2017-01-09T18:17:13                  |
    | datastore         | mysql                                |
    | datastore_version | 5.6                                  |
    | flavor            | 25                                   |
    | id                | bb0c9213-31f8-4427-8898-c644254b3642 |
    | name              | m2                                   |
    | region            | RegionOne                            |
    | server_id         | a4769ce2-4e22-4134-b958-6db6c23cb221 |
    | status            | ACTIVE                               |
    | updated           | 2017-01-09T18:17:17                  |
    | volume            | 3                                    |
    | volume_id         | 16e57e3f-b462-4db2-968b-3c284aa2751c |
    | volume_used       | 0.11                                 |
    +-------------------+--------------------------------------+

For testing later, we launch a few more instances::

    amrith@amrith-work:/opt/stack/trove/integration/scripts$ trove create m3 25 --size 3 --nic net-id=4bab02e7-87bb-4cc0-8c07-2f282c777c85
    amrith@amrith-work:/opt/stack/trove/integration/scripts$ trove create m4 25 --size 3 --nic net-id=4bab02e7-87bb-4cc0-8c07-2f282c777c85

    amrith@amrith-work:/opt/stack/trove/integration/scripts$ trove list
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | ID                                   | Name | Datastore | Datastore Version | Status | Flavor ID | Size | Region    |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 | m4   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 9ceebd62-e13d-43c5-953a-c0f24f08757e | m3   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+

In this condition, we take down the control plane and upgrade the
software running on it. This will result in a catalog upgrade. Since
this system is based on devstack, here's what that looks like::

    amrith@amrith-work:/opt/stack/trove$ git branch
    * master
      review/amrith/bp/secure-oslo-messaging-messages
    amrith@amrith-work:/opt/stack/trove$ git checkout review/amrith/bp/secure-oslo-messaging-messages
    Switched to branch 'review/amrith/bp/secure-oslo-messaging-messages'
    Your branch is ahead of 'gerrit/master' by 1 commit.
      (use "git push" to publish your local commits)
    amrith@amrith-work:/opt/stack/trove$ find . -name '*.pyc' -delete
    amrith@amrith-work:/opt/stack/trove$

    amrith@amrith-work:/opt/stack/trove$ trove-manage db_sync
    [...]
    2017-01-09 13:24:25.251 DEBUG migrate.versioning.repository [-] Config: OrderedDict([('db_settings', OrderedDict([('__name__', 'db_settings'), ('repository_id', 'Trove Migrations'), ('version_table', 'migrate_version'), ('required_dbs', "['mysql','postgres','sqlite']")]))]) from (pid=96180) __init__ /usr/local/lib/python2.7/dist-packages/migrate/versioning/repository.py:83
    2017-01-09 13:24:25.260 INFO migrate.versioning.api [-] 40 -> 41...
    2017-01-09 13:24:25.328 INFO migrate.versioning.api [-] done
    2017-01-09 13:24:25.329 DEBUG migrate.versioning.util [-] Disposing SQLAlchemy engine Engine(mysql+pymysql://root:***@127.0.0.1/trove?charset=utf8) from (pid=96180) with_engine /usr/local/lib/python2.7/dist-packages/migrate/versioning/util/__init__.py:163
    [...]

We observe that the new table in the system has the encrypted_key column::

    mysql> describe instances;
    +----------------------+--------------+------+-----+---------+-------+
    | Field                | Type         | Null | Key | Default | Extra |
    +----------------------+--------------+------+-----+---------+-------+
    | id                   | varchar(36)  | NO   | PRI | NULL    |       |
    | created              | datetime     | YES  |     | NULL    |       |
    | updated              | datetime     | YES  |     | NULL    |       |
    | name                 | varchar(255) | YES  |     | NULL    |       |
    | hostname             | varchar(255) | YES  |     | NULL    |       |
    | compute_instance_id  | varchar(36)  | YES  |     | NULL    |       |
    | task_id              | int(11)      | YES  |     | NULL    |       |
    | task_description     | varchar(255) | YES  |     | NULL    |       |
    | task_start_time      | datetime     | YES  |     | NULL    |       |
    | volume_id            | varchar(36)  | YES  |     | NULL    |       |
    | flavor_id            | varchar(255) | YES  |     | NULL    |       |
    | volume_size          | int(11)      | YES  |     | NULL    |       |
    | tenant_id            | varchar(36)  | YES  | MUL | NULL    |       |
    | server_status        | varchar(64)  | YES  |     | NULL    |       |
    | deleted              | tinyint(1)   | YES  | MUL | NULL    |       |
    | deleted_at           | datetime     | YES  |     | NULL    |       |
    | datastore_version_id | varchar(36)  | NO   | MUL | NULL    |       |
    | configuration_id     | varchar(36)  | YES  | MUL | NULL    |       |
    | slave_of_id          | varchar(36)  | YES  | MUL | NULL    |       |
    | cluster_id           | varchar(36)  | YES  | MUL | NULL    |       |
    | shard_id             | varchar(36)  | YES  |     | NULL    |       |
    | type                 | varchar(64)  | YES  |     | NULL    |       |
    | region_id            | varchar(255) | YES  |     | NULL    |       |
    | encrypted_key        | varchar(255) | YES  |     | NULL    |       |
    +----------------------+--------------+------+-----+---------+-------+


    mysql> select id, encrypted_key from instances;
    +--------------------------------------+---------------+
    | id                                   | encrypted_key |
    +--------------------------------------+---------------+
    | 13a787f2-b699-4867-a727-b3f4d8040a12 | NULL          |
    +--------------------------------------+---------------+
    1 row in set (0.00 sec)

    amrith@amrith-work:/opt/stack/trove$ sudo python setup.py install -f
    [...]

We can now relaunch the control plane software but before we do that,
we inspect the configuration parameters and disable secure RPC
messaging by adding this line into the configuration files::

    amrith@amrith-work:/etc/trove$ grep enable_secure_rpc_messaging *.conf
    trove.conf:enable_secure_rpc_messaging = False

The first thing we observe is that heartbeat messages from the
existing instance are still properly handled by the conductor and the
instance remains active::

    2017-01-09 13:26:57.742 DEBUG oslo_messaging._drivers.amqpdriver [-] received message with unique_id: eafe22c08bae485e9346ce0fbdaa4d6c from (pid=96551) __call__ /usr/local/lib/python2.7/dist-packages/oslo_messaging/_drivers/amqpdriver.py:196
    2017-01-09 13:26:57.744 DEBUG trove.conductor.manager [-] Instance ID: bb0c9213-31f8-4427-8898-c644254b3642, Payload: {u'service_status': u'running'} from (pid=96551) heartbeat /opt/stack/trove/trove/conductor/manager.py:88
    2017-01-09 13:26:57.748 DEBUG trove.conductor.manager [-] Instance bb0c9213-31f8-4427-8898-c644254b3642 sent heartbeat at 1483986416.52  from (pid=96551) _message_too_old /opt/stack/trove/trove/conductor/manager.py:54
    2017-01-09 13:26:57.750 DEBUG trove.conductor.manager [-] [Instance bb0c9213-31f8-4427-8898-c644254b3642] Rec'd message is younger than last seen. Updating. from (pid=96551) _message_too_old /opt/stack/trove/trove/conductor/manager.py:76
    2017-01-09 13:27:01.197 DEBUG oslo_messaging._drivers.amqpdriver [-] received message with unique_id: df62b76523004338876bc7b08f8b7711 from (pid=96552) __call__ /usr/local/lib/python2.7/dist-packages/oslo_messaging/_drivers/amqpdriver.py:196
    2017-01-09 13:27:01.200 DEBUG trove.conductor.manager [-] Instance ID: 9ceebd62-e13d-43c5-953a-c0f24f08757e, Payload: {u'service_status': u'running'} from (pid=96552) heartbeat /opt/stack/trove/trove/conductor/manager.py:88
    2017-01-09 13:27:01.219 DEBUG oslo_db.sqlalchemy.engines [-] Parent process 96542 forked (96552) with an open database connection, which is being discarded and recreated. from (pid=96552) checkout /usr/local/lib/python2.7/dist-packages/oslo_db/sqlalchemy/engines.py:362
    2017-01-09 13:27:01.225 DEBUG trove.conductor.manager [-] Instance 9ceebd62-e13d-43c5-953a-c0f24f08757e sent heartbeat at 1483986419.99  from (pid=96552) _message_too_old /opt/stack/trove/trove/conductor/manager.py:54
    2017-01-09 13:27:01.231 DEBUG trove.conductor.manager [-] [Instance 9ceebd62-e13d-43c5-953a-c0f24f08757e] Rec'd message is younger than last seen. Updating. from (pid=96552) _message_too_old /opt/stack/trove/trove/conductor/manager.py:76

    amrith@amrith-work:/etc/trove$ trove list
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | ID                                   | Name | Datastore | Datastore Version | Status | Flavor ID | Size | Region    |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 | m4   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 9ceebd62-e13d-43c5-953a-c0f24f08757e | m3   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+

    amrith@amrith-work:/etc/trove$ trove show m2
    +-------------------+--------------------------------------+
    | Property          | Value                                |
    +-------------------+--------------------------------------+
    | created           | 2017-01-09T18:17:13                  |
    | datastore         | mysql                                |
    | datastore_version | 5.6                                  |
    | flavor            | 25                                   |
    | id                | bb0c9213-31f8-4427-8898-c644254b3642 |
    | name              | m2                                   |
    | region            | RegionOne                            |
    | server_id         | a4769ce2-4e22-4134-b958-6db6c23cb221 |
    | status            | ACTIVE                               |
    | updated           | 2017-01-09T18:17:17                  |
    | volume            | 3                                    |
    | volume_id         | 16e57e3f-b462-4db2-968b-3c284aa2751c |
    | volume_used       | 0.11                                 |
    +-------------------+--------------------------------------+

We now launch a new instance, recall that secure_rpc_messaging is
disabled::

    amrith@amrith-work:/etc/trove$ trove create m10 25 --size 3 --nic net-id=4bab02e7-87bb-4cc0-8c07-2f282c777c85
    +-------------------+--------------------------------------+
    | Property          | Value                                |
    +-------------------+--------------------------------------+
    | created           | 2017-01-09T18:28:56                  |
    | datastore         | mysql                                |
    | datastore_version | 5.6                                  |
    | flavor            | 25                                   |
    | id                | 514ef051-0bf7-48a5-adcf-071d4a6625fb |
    | name              | m10                                  |
    | region            | RegionOne                            |
    | server_id         | None                                 |
    | status            | BUILD                                |
    | updated           | 2017-01-09T18:28:56                  |
    | volume            | 3                                    |
    | volume_id         | None                                 |
    +-------------------+--------------------------------------+

Observe that the task manager does not create a password for the instance::

    2017-01-09 13:29:00.111 INFO trove.instance.models [-] Resetting task status to NONE on instance 514ef051-0bf7-48a5-adcf-071d4a6625fb.
    2017-01-09 13:29:00.115 DEBUG trove.db.models [-] Saving DBInstance: {u'region_id': u'RegionOne', u'cluster_id': None, u'shard_id': None, u'deleted_at': None, u'id': u'514ef051-0bf7-48a5-adcf-071d4a6625fb', u'datastore_version_id': u'4a881cb5-9e48-4cb2-a209-4283ed44eb01', 'errors': {}, u'hostname': None, u'server_status': None, u'task_description': u'No tasks for the instance.', u'volume_size': 3, u'type': None, u'updated': datetime.datetime(2017, 1, 9, 18, 29, 0, 114971), '_sa_instance_state': <sqlalchemy.orm.state.InstanceState object at 0x7f460dbca410>, u'encrypted_key': None, u'deleted': 0, u'configuration_id': None, u'volume_id': u'cee2e17b-80fa-48e5-a488-da8b7809373a', u'slave_of_id': None, u'task_start_time': None, u'name': u'm10', u'task_id': 1, u'created': datetime.datetime(2017, 1, 9, 18, 28, 56), u'tenant_id': u'56cca8484d3e48869126ada4f355c284', u'compute_instance_id': u'2452263e-3d33-48ec-8f24-2851fe74db28', u'flavor_id': u'25'} from (pid=96635) save /opt/stack/trove/trove/db/models.py:64


The configuration file for this instance is::

    amrith@m10:~$ cat /etc/trove/conf.d/guest_info.conf
    [DEFAULT]
    guest_id=514ef051-0bf7-48a5-adcf-071d4a6625fb
    datastore_manager=mysql
    tenant_id=56cca8484d3e48869126ada4f355c284

We can now shutdown the control plane again and enable the secure RPC
capability. Observe that we've just commented out the lines (below)::

    trove.conf:# enable_secure_rpc_messaging = False

And create another database instance::

    amrith@amrith-work:/etc/trove$ trove create m20 25 --size 3 --nic net-id=4bab02e7-87bb-4cc0-8c07-2f282c777c85
    +-------------------+--------------------------------------+
    | Property          | Value                                |
    +-------------------+--------------------------------------+
    | created           | 2017-01-09T18:31:48                  |
    | datastore         | mysql                                |
    | datastore_version | 5.6                                  |
    | flavor            | 25                                   |
    | id                | 792fa220-2a40-4831-85af-cfb0ded8033c |
    | name              | m20                                  |
    | region            | RegionOne                            |
    | server_id         | None                                 |
    | status            | BUILD                                |
    | updated           | 2017-01-09T18:31:48                  |
    | volume            | 3                                    |
    | volume_id         | None                                 |
    +-------------------+--------------------------------------+

Observe that a unique per-instance encryption key was created for this
instance::

  2017-01-09 13:31:52.474 DEBUG trove.db.models [-] Saving DBInstance: {u'region_id': u'RegionOne', u'cluster_id': None, u'shard_id': None, u'deleted_at': None, u'id': u'792fa220-2a40-4831-85af-cfb0ded8033c', u'datastore_version_id': u'4a881cb5-9e48-4cb2-a209-4283ed44eb01', 'errors': {}, u'hostname': None, u'server_status': None, u'task_description': u'No tasks for the instance.', u'volume_size': 3, u'type': None, u'updated': datetime.datetime(2017, 1, 9, 18, 31, 52, 473552), '_sa_instance_state': <sqlalchemy.orm.state.InstanceState object at 0x7fdb14d44550>, u'encrypted_key': u'fVpHrkUIjVsXe7Fj7Lm4u2xnJUsWX2rMC9GL0AppILJINBZxLvkowY8FOa+asKS+8pWb4iNyukQQ4AQoLEUHUQ==', u'deleted': 0, u'configuration_id': None, u'volume_id': u'4cd563dc-fe08-477b-828f-120facf4351b', u'slave_of_id': None, u'task_start_time': None, u'name': u'm20', u'task_id': 1, u'created': datetime.datetime(2017, 1, 9, 18, 31, 49), u'tenant_id': u'56cca8484d3e48869126ada4f355c284', u'compute_instance_id': u'1e62a192-83d3-43fd-b32e-b5ee2fa4e24b', u'flavor_id': u'25'} from (pid=97562) save /opt/stack/trove/trove/db/models.py:64

And the configuration file on that instance includes an encryption key::

    amrith@m20:~$ cat /etc/trove/conf.d/guest_info.conf
    [DEFAULT]
    guest_id=792fa220-2a40-4831-85af-cfb0ded8033c
    datastore_manager=mysql
    tenant_id=56cca8484d3e48869126ada4f355c284
    instance_rpc_encr_key=eRz43LwE6eaxIbBlA2pNukzPjSdcQkVi

    amrith@amrith-work:/etc/trove$ trove list
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | ID                                   | Name | Datastore | Datastore Version | Status | Flavor ID | Size | Region    |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | 514ef051-0bf7-48a5-adcf-071d4a6625fb | m10  | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 | m4   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 792fa220-2a40-4831-85af-cfb0ded8033c | m20  | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 9ceebd62-e13d-43c5-953a-c0f24f08757e | m3   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+

At this point communication between API service and Task Manager, and
between the control plane and instance m20 is encrypted but
communication between control plane and all other instances is not
encrypted.

In this condition we can attempt some operations on the various
instances. First with the legacy instances created on software that
predated the secure RPC mechanism::

    amrith@amrith-work:/etc/trove$ trove database-list m2
    +------+
    | Name |
    +------+
    +------+
    amrith@amrith-work:/etc/trove$ trove database-create m2 foo2
    amrith@amrith-work:/etc/trove$ trove database-list m2
    +------+
    | Name |
    +------+
    | foo2 |
    +------+

And at the same time with the instance m10 which is created with the
current software but without RPC encryption::

    amrith@amrith-work:/etc/trove$ trove database-list m10
    +------+
    | Name |
    +------+
    +------+
    amrith@amrith-work:/etc/trove$ trove database-create m10 foo10
    amrith@amrith-work:/etc/trove$ trove database-list m10
    +-------+
    | Name  |
    +-------+
    | foo10 |
    +-------+
    amrith@amrith-work:/etc/trove$

And finally with an instance that uses encrypted RPC communications::

    amrith@amrith-work:/etc/trove$ trove database-list m20
    +------+
    | Name |
    +------+
    +------+
    amrith@amrith-work:/etc/trove$ trove database-create m20 foo20
    amrith@amrith-work:/etc/trove$ trove database-list m20
    +-------+
    | Name  |
    +-------+
    | foo20 |
    +-------+

Finally, we can upgrade an instance that has no encryption to have rpc
encryption::

    amrith@amrith-work:/etc/trove$ trove datastore-list
    +--------------------------------------+------------------+
    | ID                                   | Name             |
    +--------------------------------------+------------------+
    | 8e052edb-5f14-4aec-9149-0a80a30cf5e4 | mysql            |
    +--------------------------------------+------------------+
    amrith@amrith-work:/etc/trove$ trove datastore-version-list mysql
    +--------------------------------------+------------------+
    | ID                                   | Name             |
    +--------------------------------------+------------------+
    | 4a881cb5-9e48-4cb2-a209-4283ed44eb01 | 5.6              |
    +--------------------------------------+------------------+

Let's look at instance m2::

    mysql> select id, name, encrypted_key from instances where id = 'bb0c9213-31f8-4427-8898-c644254b3642';
    +--------------------------------------+------+---------------+
    | id                                   | name | encrypted_key |
    +--------------------------------------+------+---------------+
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | NULL          |
    +--------------------------------------+------+---------------+
    1 row in set (0.00 sec)

    amrith@amrith-work:/etc/trove$ trove upgrade m2 4a881cb5-9e48-4cb2-a209-4283ed44eb01

    amrith@amrith-work:/etc/trove$ trove list
    +--------------------------------------+------+-----------+-------------------+---------+-----------+------+-----------+
    | ID                                   | Name | Datastore | Datastore Version | Status  | Flavor ID | Size | Region    |
    +--------------------------------------+------+-----------+-------------------+---------+-----------+------+-----------+
    | 514ef051-0bf7-48a5-adcf-071d4a6625fb | m10  | mysql     | 5.6               | ACTIVE  | 25        |    3 | RegionOne |
    | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 | m4   | mysql     | 5.6               | ACTIVE  | 25        |    3 | RegionOne |
    | 792fa220-2a40-4831-85af-cfb0ded8033c | m20  | mysql     | 5.6               | ACTIVE  | 25        |    3 | RegionOne |
    | 9ceebd62-e13d-43c5-953a-c0f24f08757e | m3   | mysql     | 5.6               | ACTIVE  | 25        |    3 | RegionOne |
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | mysql     | 5.6               | UPGRADE | 25        |    3 | RegionOne |
    +--------------------------------------+------+-----------+-------------------+---------+-----------+------+-----------+

    amrith@amrith-work:/etc/trove$ nova list
    +--------------------------------------+------+---------+------------+-------------+--------------------+
    | ID                                   | Name | Status  | Task State | Power State | Networks           |
    +--------------------------------------+------+---------+------------+-------------+--------------------+
    [...]
    | a4769ce2-4e22-4134-b958-6db6c23cb221 | m2   | REBUILD | rebuilding | Running     | public=172.24.4.4  |
    [...]
    +--------------------------------------+------+---------+------------+-------------+--------------------+


    2017-01-09 13:47:24.337 DEBUG trove.db.models [-] Saving DBInstance: {u'region_id': u'RegionOne', u'cluster_id': None, u'shard_id': None, u'deleted_at': None, u'id': u'bb0c9213-31f8-4427-8898-c644254b3642', u'datastore_version_id': u'4a881cb5-9e48-4cb2-a209-4283ed44eb01', 'errors': {}, u'hostname': None, u'server_status': None, u'task_description': u'Upgrading the instance.', u'volume_size': 3, u'type': None, u'updated': datetime.datetime(2017, 1, 9, 18, 47, 24, 337400), '_sa_instance_state': <sqlalchemy.orm.state.InstanceState object at 0x7fdb14d44150>, u'encrypted_key': u'gMrlHkEVxKgEFMTabzZr2TLJ6r5+wgfJfhohs7K/BzutWxs1wXfBswyV5Bgw4qeD212msmgSdOUCFov5otgzyg==', u'deleted': 0, u'configuration_id': None, u'volume_id': u'16e57e3f-b462-4db2-968b-3c284aa2751c', u'slave_of_id': None, u'task_start_time': None, u'name': u'm2', u'task_id': 89, u'created': datetime.datetime(2017, 1, 9, 18, 17, 13), u'tenant_id': u'56cca8484d3e48869126ada4f355c284', u'compute_instance_id': u'a4769ce2-4e22-4134-b958-6db6c23cb221', u'flavor_id': u'25'} from (pid=97562) save /opt/stack/trove/trove/db/models.py:64
    2017-01-09 13:47:24.347 DEBUG trove.taskmanager.models [-] Generated unique RPC encryption key for instance = bb0c9213-31f8-4427-8898-c644254b3642, key = gMrlHkEVxKgEFMTabzZr2TLJ6r5+wgfJfhohs7K/BzutWxs1wXfBswyV5Bgw4qeD212msmgSdOUCFov5otgzyg== from (pid=97562) upgrade /opt/stack/trove/trove/taskmanager/models.py:1440
    2017-01-09 13:47:24.350 DEBUG trove.taskmanager.models [-] Rebuilding instance m2(bb0c9213-31f8-4427-8898-c644254b3642) with image ea05cba7-2f70-4745-abea-136d7bcc16c7. from (pid=97562) upgrade /opt/stack/trove/trove/taskmanager/models.py:1445

The instance now has an encryption key in its configuration::

    amrith@m2:~$ cat /etc/trove/conf.d/guest_info.conf
    [DEFAULT]
    guest_id=bb0c9213-31f8-4427-8898-c644254b3642
    datastore_manager=mysql
    tenant_id=56cca8484d3e48869126ada4f355c284
    instance_rpc_encr_key=pN2hHEl171ngyD0mPvyV1xKJF2im01Gv

    amrith@amrith-work:/etc/trove$ trove list
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | ID                                   | Name | Datastore | Datastore Version | Status | Flavor ID | Size | Region    |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    [...]
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    [...]
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+

    amrith@amrith-work:/etc/trove$ trove show m2
    +-------------------+--------------------------------------+
    | Property          | Value                                |
    +-------------------+--------------------------------------+
    | created           | 2017-01-09T18:17:13                  |
    | datastore         | mysql                                |
    | datastore_version | 5.6                                  |
    | flavor            | 25                                   |
    | id                | bb0c9213-31f8-4427-8898-c644254b3642 |
    | name              | m2                                   |
    | region            | RegionOne                            |
    | server_id         | a4769ce2-4e22-4134-b958-6db6c23cb221 |
    | status            | ACTIVE                               |
    | updated           | 2017-01-09T18:50:07                  |
    | volume            | 3                                    |
    | volume_id         | 16e57e3f-b462-4db2-968b-3c284aa2751c |
    | volume_used       | 0.13                                 |
    +-------------------+--------------------------------------+

    amrith@amrith-work:/etc/trove$ trove database-list m2
    +------+
    | Name |
    +------+
    | foo2 |
    +------+

We can similarly upgrade m4::

    2017-01-09 13:51:43.078 DEBUG trove.instance.models [-] Instance 6d55ab3a-267f-4b95-8ada-33fc98fd1767 service status is running. from (pid=97562) load_instance /opt/stack/trove/trove/instance/models.py:534
    2017-01-09 13:51:43.083 DEBUG trove.taskmanager.models [-] Upgrading instance m4(6d55ab3a-267f-4b95-8ada-33fc98fd1767) to new datastore version 5.6(4a881cb5-9e48-4cb2-a209-4283ed44eb01) from (pid=97562) upgrade /opt/stack/trove/trove/taskmanager/models.py:1410
    2017-01-09 13:51:43.087 DEBUG trove.guestagent.api [-] Sending the call to prepare the guest for upgrade. from (pid=97562) pre_upgrade /opt/stack/trove/trove/guestagent/api.py:351
    2017-01-09 13:51:43.087 DEBUG trove.guestagent.api [-] Calling pre_upgrade with timeout 600 from (pid=97562) _call /opt/stack/trove/trove/guestagent/api.py:86
    2017-01-09 13:51:43.088 DEBUG oslo_messaging._drivers.amqpdriver [-] CALL msg_id: 41dbb7fff3dc4f8fa69d8b5f219809e0 exchange 'trove' topic 'guestagent.6d55ab3a-267f-4b95-8ada-33fc98fd1767' from (pid=97562) _send /usr/local/lib/python2.7/dist-packages/oslo_messaging/_drivers/amqpdriver.py:442
    2017-01-09 13:51:45.452 DEBUG oslo_messaging._drivers.amqpdriver [-] received reply msg_id: 41dbb7fff3dc4f8fa69d8b5f219809e0 from (pid=97562) __call__ /usr/local/lib/python2.7/dist-packages/oslo_messaging/_drivers/amqpdriver.py:299
    2017-01-09 13:51:45.452 DEBUG trove.guestagent.api [-] Result is {u'mount_point': u'/var/lib/mysql', u'save_etc_dir': u'/var/lib/mysql/etc', u'home_save': u'/var/lib/mysql/trove_user', u'save_dir': u'/var/lib/mysql/etc_mysql'}. from (pid=97562) _call /opt/stack/trove/trove/guestagent/api.py:91
    2017-01-09 13:51:45.544 DEBUG trove.db.models [-] Saving DBInstance: {u'region_id': u'RegionOne', u'cluster_id': None, u'shard_id': None, u'deleted_at': None, u'id': u'6d55ab3a-267f-4b95-8ada-33fc98fd1767', u'datastore_version_id': u'4a881cb5-9e48-4cb2-a209-4283ed44eb01', 'errors': {}, u'hostname': None, u'server_status': None, u'task_description': u'Upgrading the instance.', u'volume_size': 3, u'type': None, u'updated': datetime.datetime(2017, 1, 9, 18, 51, 45, 544496), '_sa_instance_state': <sqlalchemy.orm.state.InstanceState object at 0x7fdb14972c10>, u'encrypted_key': u'0gBkJl5Aqb4kFIPeJDMTNIymEUuUUB8NBksecTiYyQl+Ibrfi7ME8Bi58q2n61AxbG2coOqp97ETjHRyN7mYTg==', u'deleted': 0, u'configuration_id': None, u'volume_id': u'b7dc17b5-d0a8-47bb-aef4-ef9432c269e9', u'slave_of_id': None, u'task_start_time': None, u'name': u'm4', u'task_id': 89, u'created': datetime.datetime(2017, 1, 9, 18, 20, 58), u'tenant_id': u'56cca8484d3e48869126ada4f355c284', u'compute_instance_id': u'f43bba63-3be6-4993-b2d0-4ddfb7818d27', u'flavor_id': u'25'} from (pid=97562) save /opt/stack/trove/trove/db/models.py:64
    2017-01-09 13:51:45.557 DEBUG trove.taskmanager.models [-] Generated unique RPC encryption key for instance = 6d55ab3a-267f-4b95-8ada-33fc98fd1767, key = 0gBkJl5Aqb4kFIPeJDMTNIymEUuUUB8NBksecTiYyQl+Ibrfi7ME8Bi58q2n61AxbG2coOqp97ETjHRyN7mYTg== from (pid=97562) upgrade /opt/stack/trove/trove/taskmanager/models.py:1440
    2017-01-09 13:51:45.560 DEBUG trove.taskmanager.models [-] Rebuilding instance m4(6d55ab3a-267f-4b95-8ada-33fc98fd1767) with image ea05cba7-2f70-4745-abea-136d7bcc16c7. from (pid=97562) upgrade /opt/stack/trove/trove/taskmanager/models.py:1445

    amrith@amrith-work:/etc/trove$ nova list
    +--------------------------------------+------+---------+------------+-------------+--------------------+
    | ID                                   | Name | Status  | Task State | Power State | Networks           |
    +--------------------------------------+------+---------+------------+-------------+--------------------+
    [...]
    | f43bba63-3be6-4993-b2d0-4ddfb7818d27 | m4   | REBUILD | rebuilding | Running     | public=172.24.4.11 |
    [...]
    +--------------------------------------+------+---------+------------+-------------+--------------------+

    2017-01-09 13:53:26.581 DEBUG trove.guestagent.api [-] Recover the guest after upgrading the guest's image. from (pid=97562) post_upgrade /opt/stack/trove/trove/guestagent/api.py:359
    2017-01-09 13:53:26.581 DEBUG trove.guestagent.api [-] Recycling the client ... from (pid=97562) post_upgrade /opt/stack/trove/trove/guestagent/api.py:361
    2017-01-09 13:53:26.581 DEBUG trove.guestagent.api [-] Calling post_upgrade with timeout 600 from (pid=97562) _call /opt/stack/trove/trove/guestagent/api.py:86
    2017-01-09 13:53:26.583 DEBUG oslo_messaging._drivers.amqpdriver [-] CALL msg_id: 2e9ccc88715b4b98848a017e19b2938d exchange 'trove' topic 'guestagent.6d55ab3a-267f-4b95-8ada-33fc98fd1767' from (pid=97562) _send /usr/local/lib/python2.7/dist-packages/oslo_messaging/_drivers/amqpdriver.py:442

    mysql> select id, name, encrypted_key from instances where name in ('m2', 'm4', 'm10', 'm20');
    +--------------------------------------+------+------------------------------------------------------------------------------------------+
    | id                                   | name | encrypted_key                                                                            |
    +--------------------------------------+------+------------------------------------------------------------------------------------------+
    | 514ef051-0bf7-48a5-adcf-071d4a6625fb | m10  | NULL                                                                                     |
    | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 | m4   | 0gBkJl5Aqb4kFIPeJDMTNIymEUuUUB8NBksecTiYyQl+Ibrfi7ME8Bi58q2n61AxbG2coOqp97ETjHRyN7mYTg== |
    | 792fa220-2a40-4831-85af-cfb0ded8033c | m20  | fVpHrkUIjVsXe7Fj7Lm4u2xnJUsWX2rMC9GL0AppILJINBZxLvkowY8FOa+asKS+8pWb4iNyukQQ4AQoLEUHUQ== |
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | gMrlHkEVxKgEFMTabzZr2TLJ6r5+wgfJfhohs7K/BzutWxs1wXfBswyV5Bgw4qeD212msmgSdOUCFov5otgzyg== |
    +--------------------------------------+------+------------------------------------------------------------------------------------------+

    amrith@amrith-work:/etc/trove$ trove list
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | ID                                   | Name | Datastore | Datastore Version | Status | Flavor ID | Size | Region    |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+
    | 514ef051-0bf7-48a5-adcf-071d4a6625fb | m10  | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 | m4   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | 792fa220-2a40-4831-85af-cfb0ded8033c | m20  | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    | bb0c9213-31f8-4427-8898-c644254b3642 | m2   | mysql     | 5.6               | ACTIVE | 25        |    3 | RegionOne |
    +--------------------------------------+------+-----------+-------------------+--------+-----------+------+-----------+

Inspecting which instances are using secure RPC communications
--------------------------------------------------------------

An additional field is returned in the trove show command output to
indicate whether any given instance is using secure RPC communication
or not.

.. note::

  This field is only returned if the user is an 'admin'. Non admin
  users do not see the field.

::

    amrith@amrith-work:/opt/stack/trove$ trove show m20
    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-01-09T18:31:49                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | True                                 |
    | flavor                  | 25                                   |
    | id                      | 792fa220-2a40-4831-85af-cfb0ded8033c |
    | name                    | m20                                  |
    | region                  | RegionOne                            |
    | server_id               | 1e62a192-83d3-43fd-b32e-b5ee2fa4e24b |
    | status                  | ACTIVE                               |
    | updated                 | 2017-01-09T18:31:52                  |
    | volume                  | 3                                    |
    | volume_id               | 4cd563dc-fe08-477b-828f-120facf4351b |
    | volume_used             | 0.11                                 |
    +-------------------------+--------------------------------------+
    amrith@amrith-work:/opt/stack/trove$ trove show m10
    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-01-09T18:28:56                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | False                                |
    | flavor                  | 25                                   |
    | id                      | 514ef051-0bf7-48a5-adcf-071d4a6625fb |
    | name                    | m10                                  |
    | region                  | RegionOne                            |
    | server_id               | 2452263e-3d33-48ec-8f24-2851fe74db28 |
    | status                  | ACTIVE                               |
    | updated                 | 2017-01-09T18:29:00                  |
    | volume                  | 3                                    |
    | volume_id               | cee2e17b-80fa-48e5-a488-da8b7809373a |
    | volume_used             | 0.11                                 |
    +-------------------------+--------------------------------------+
    amrith@amrith-work:/opt/stack/trove$ trove show m2
    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-01-09T18:17:13                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | True                                 |
    | flavor                  | 25                                   |
    | id                      | bb0c9213-31f8-4427-8898-c644254b3642 |
    | name                    | m2                                   |
    | region                  | RegionOne                            |
    | server_id               | a4769ce2-4e22-4134-b958-6db6c23cb221 |
    | status                  | ACTIVE                               |
    | updated                 | 2017-01-09T18:50:07                  |
    | volume                  | 3                                    |
    | volume_id               | 16e57e3f-b462-4db2-968b-3c284aa2751c |
    | volume_used             | 0.13                                 |
    +-------------------------+--------------------------------------+
    amrith@amrith-work:/opt/stack/trove$ trove show m4
    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-01-09T18:20:58                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | True                                 |
    | flavor                  | 25                                   |
    | id                      | 6d55ab3a-267f-4b95-8ada-33fc98fd1767 |
    | name                    | m4                                   |
    | region                  | RegionOne                            |
    | server_id               | f43bba63-3be6-4993-b2d0-4ddfb7818d27 |
    | status                  | ACTIVE                               |
    | updated                 | 2017-01-09T18:54:30                  |
    | volume                  | 3                                    |
    | volume_id               | b7dc17b5-d0a8-47bb-aef4-ef9432c269e9 |
    | volume_used             | 0.13                                 |
    +-------------------------+--------------------------------------+
    amrith@amrith-work:/opt/stack/trove$

In the API response, note that the additional key
"encrypted_rpc_messaging" has been added (as below).

.. note::

   This field is only returned if the user is an 'admin'. Non admin
   users do not see the field.

::

   RESP BODY: {"instance": {"status": "ACTIVE", "updated": "2017-01-09T18:29:00", "name": "m10", "links": [{"href": "https://192.168.126.130:8779/v1.0/56cca8484d3e48869126ada4f355c284/instances/514ef051-0bf7-48a5-adcf-071d4a6625fb", "rel": "self"}, {"href": "https://192.168.126.130:8779/instances/514ef051-0bf7-48a5-adcf-071d4a6625fb", "rel": "bookmark"}], "created": "2017-01-09T18:28:56", "region": "RegionOne", "server_id": "2452263e-3d33-48ec-8f24-2851fe74db28", "id": "514ef051-0bf7-48a5-adcf-071d4a6625fb", "volume": {"used": 0.11, "size": 3}, "volume_id": "cee2e17b-80fa-48e5-a488-da8b7809373a", "flavor": {"id": "25"}, "datastore": {"version": "5.6", "type": "mysql"}, "encrypted_rpc_messaging": false}}
