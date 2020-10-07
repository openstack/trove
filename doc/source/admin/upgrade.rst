=============
Trove upgrade
=============

Before upgrading Trove, it is recommended to read
https://docs.openstack.org/operations-guide/ops-upgrades.html first.

Normally, before Trove service upgrade, a new guest image needs to be rebuilt
and used to rebuild the guest instance when the interfaces between Trove
controller and guest agent change. Otherwise, the newer version Trove
controller can't talk to the older version guest agent.

Basically, the Trove service upgrade process consists of the following steps:

#. Build new guest image based on new Trove code.
#. Trove database migration.
#. Prepare service config files and upgrade Trove controller services.
#. Register new datastore version using the new guest image.
#. Upgrade Trove instance (trove-guestagent).

Upgrade Trove in DevStack
-------------------------

This is an example in DevStack to provide a basic idea of Trove upgrade
process. The commands in each step could be different between different Trove
deployment environments.

Before upgrading
~~~~~~~~~~~~~~~~

If upgrading Trove from Ussuri to Victoria, the end users need to backup their
instances first and re-create new instances using backups after upgrade. From
Victoria onwards, the instance (trove-guestagent service) upgrade could happen
in place and can be triggered by the cloud administrator.

* If you are using Trove Ussuri.

  .. note::

     The latest version of python-troveclient to communicate with Trove Ussuri
     is 3.3.1. Some CLI parameters are changed since Victoria release.

  In this example, we create a new db instance and use the instance for upgrade
  testing.

  .. code-block:: console

      $ openstack database instance create test \
          $flavorid \
          --size 1 \
          --nic net-id=$netid \
          --datastore mysql --datastore_version 5.7 \
          --databases testdb --users user:password \
          --is-public
      $ openstack database instance list
      +--------------------------------------+------+-----------+-------------------+---------+---------------------------+--------------------------------------+------+-----------+
      | ID                                   | Name | Datastore | Datastore Version | Status  | Addresses                 | Flavor ID                            | Size | Region    |
      +--------------------------------------+------+-----------+-------------------+---------+---------------------------+--------------------------------------+------+-----------+
      | adae9a37-2c14-4dcb-9abd-66b8c3d5808b | test | mysql     | 5.7               | HEALTHY | 10.111.0.27, 172.30.5.107 | 55d9c9ac-b136-4dcf-9a1d-ecb7077697f9 |    1 | RegionOne |
      +--------------------------------------+------+-----------+-------------------+---------+---------------------------+--------------------------------------+------+-----------+

  In order to test upgrade, we insert some data to the database:

  .. code-block:: console

      $ ip=172.30.5.107
      $ mysql -u user -ppassword -h $ip testdb
      CREATE TABLE Persons (PersonID int, LastName varchar(255), FirstName varchar(255), Address varchar(255), City varchar(255));
      insert into Persons VALUES (1, 'Kong', 'Lingxian', '150 Willis Street', 'Wellington');

  Now we create a backup for the instance:

  .. code-block:: console

      $ dbid=adae9a37-2c14-4dcb-9abd-66b8c3d5808b
      $ openstack database backup create $dbid backup-01
      $ openstack database backup list
      +--------------------------------------+--------------------------------------+-----------+-----------+-----------+---------------------+
      | ID                                   | Instance ID                          | Name      | Status    | Parent ID | Updated             |
      +--------------------------------------+--------------------------------------+-----------+-----------+-----------+---------------------+
      | 5c21437f-02b3-43e0-8108-99a3497d68ad | adae9a37-2c14-4dcb-9abd-66b8c3d5808b | backup-01 | COMPLETED | None      | 2020-08-13T10:30:09 |
      +--------------------------------------+--------------------------------------+-----------+-----------+-----------+---------------------+
      $ openstack database backup show 5c21437f-02b3-43e0-8108-99a3497d68ad
      +----------------------+-----------------------------------------------------------------------------------------------------------------------------------+
      | Field                | Value                                                                                                                             |
      +----------------------+-----------------------------------------------------------------------------------------------------------------------------------+
      | created              | 2020-08-13T10:30:02                                                                                                               |
      | datastore            | mysql                                                                                                                             |
      | datastore_version    | 5.7                                                                                                                               |
      | datastore_version_id | 8008a4ca-9124-40ea-a24b-13d53fc9b355                                                                                              |
      | description          | None                                                                                                                              |
      | id                   | 5c21437f-02b3-43e0-8108-99a3497d68ad                                                                                              |
      | instance_id          | adae9a37-2c14-4dcb-9abd-66b8c3d5808b                                                                                              |
      | locationRef          | http://10.0.19.85:8080/v1/AUTH_7e42f87f5d504da9a70cf781a98e0179/database_backups/5c21437f-02b3-43e0-8108-99a3497d68ad.xbstream.gz |
      | name                 | backup-01                                                                                                                         |
      | parent_id            | None                                                                                                                              |
      | size                 | 0.12                                                                                                                              |
      | status               | COMPLETED                                                                                                                         |
      | updated              | 2020-08-13T10:30:09                                                                                                               |
      +----------------------+-----------------------------------------------------------------------------------------------------------------------------------+
      $ openstack object list database_backups
      +--------------------------------------------------+
      | Name                                             |
      +--------------------------------------------------+
      | 5c21437f-02b3-43e0-8108-99a3497d68ad.xbstream.gz |
      +--------------------------------------------------+

* If you are using Trove Victoria or newer version.

  TBD.

Upgrade Trove services
~~~~~~~~~~~~~~~~~~~~~~

#. Go to the Trove source code directory, checkout to ``stable/victoria``
   branch.

#. Build new guest image based on new Trove code.

   Here we are building a dev-mode guest image.

   .. code-block:: console

      $ stackdir=/opt/stack
      $ $stackdir/trove/integration/scripts/trovestack build-image ubuntu bionic true ubuntu

#. Trove database migration.

   On trove controller node:

   .. code-block:: console

      $ trove-manage --config-file /etc/trove/trove.conf db_upgrade

#. Prepare service config files and upgrade Trove controller services.

   You need to read Trove release notes to check if there are extra required
   config options in the new release.

   After configuration, restart Trove services:

   .. code-block:: console

      $ sudo systemctl restart apache2.service; sudo systemctl restart devstack@tr-*

#. Register new datastore version using the new guest image.

   We use MySQL datastore for an example. The following commands should be
   running using trove service tenant credentials.

   .. code-block:: console

      $ imageid=$(openstack image create trove-guest-victoria-ubuntu-bionic-dev \
          --private \
          --disk-format qcow2 --container-format bare \
          --file ${image-path} \
          --property hw_rng_model='virtio' \
          --tag trove \
          -c id -f value)
      $ trove-manage datastore_version_update mysql 5.7.29 mysql $imageid "" "" 1
      $ trove-manage db_load_datastore_config_parameters mysql 5.7.29 $stackdir/trove/trove/templates/mysql/validation-rules.json

Upgrade Trove guest agent
~~~~~~~~~~~~~~~~~~~~~~~~~

* If you are upgrading from Ussuri.

  .. note::

     It's recommended to upgrade python-troveclient to the latest version
     first. You may notice some parameters are different with the examples
     above.

  In the example above, we have created a instance and backup before upgrading.
  Now it's time to create new instance using the backup.

  .. code-block:: console

      $ openstack database instance create test-upgrade \
        --flavor $flavorid \
        --size 1 \
        --nic net-id=$netid \
        --datastore mysql --datastore-version 5.7.29 \
        --is-public \
        --backup 5c21437f-02b3-43e0-8108-99a3497d68ad
      $ openstack database instance list
      +--------------------------------------+--------------+-----------+-------------------+---------+--------+------------------------------------------------------------------------------------------------+--------------------------------------+------+------+
      | ID                                   | Name         | Datastore | Datastore Version | Status  | Public | Addresses                                                                                      | Flavor ID                            | Size | Role |
      +--------------------------------------+--------------+-----------+-------------------+---------+--------+------------------------------------------------------------------------------------------------+--------------------------------------+------+------+
      | 93eb232a-4cd1-4273-87ab-2ee48afbaa0b | test-upgrade | mysql     | 5.7.29            | HEALTHY | True   | [{'address': '10.111.0.52', 'type': 'private'}, {'address': '172.30.5.204', 'type': 'public'}] | 55d9c9ac-b136-4dcf-9a1d-ecb7077697f9 |    1 |      |
      | adae9a37-2c14-4dcb-9abd-66b8c3d5808b | test         | mysql     | 5.7               | HEALTHY | True   | [{'address': '10.111.0.27', 'type': 'private'}, {'address': '172.30.5.107', 'type': 'public'}] | 55d9c9ac-b136-4dcf-9a1d-ecb7077697f9 |    1 |      |
      +--------------------------------------+--------------+-----------+-------------------+---------+--------+------------------------------------------------------------------------------------------------+--------------------------------------+------+------+

  Query the database to make sure there is no data missing.

  .. code-block:: console

      $ ip=172.30.5.204
      $ mysql -u user -ppassword -h $ip testdb -e "select * from Persons;"
      +----------+----------+-----------+-------------------+------------+
      | PersonID | LastName | FirstName | Address           | City       |
      +----------+----------+-----------+-------------------+------------+
      |        1 | Kong     | Lingxian  | 150 Willis Street | Wellington |
      +----------+----------+-----------+-------------------+------------+

  After the new db instance is working as expected, the old one (and its
  backups) could be removed. Your database client needs to use the new address
  in the connection string unless database dns is supported in the future.

* If you are upgrading from Victoria or newer release.

  TBD.