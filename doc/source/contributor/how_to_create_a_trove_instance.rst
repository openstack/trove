.. _create_trove_instance:

==============================
How to create a trove instance
==============================

While creating a trove instance, I often have problems with cinder
volumes and nova servers, this is due to my lack of knowledge in the area.
This post is to help describe my journey on creating a trove instance.

----------------
Installing trove
----------------

I use the integration tools provided by trove to install the required services.
This is already covered in the install guide.

Install trove

.. code-block:: bash

    /trove/integration/scripts$ ./trovestack install

Once that completes, I use the command kick-start that gets a datastore
ready for us to use and target for our trove instance. This shows the
mysql datastore.

.. code-block:: bash

    /trove/integration/scripts$ ./trovestack kick-start mysql

Note: This command doesn't give you a completion message.

You can view the available datastores by running the following command

.. code-block:: bash

    $ trove datastore-list

    +--------------------------------------+------------------+
    | ID                                   | Name             |
    +--------------------------------------+------------------+
    | 137c27ee-d491-4a54-90ab-06307e9f6bf6 | mysql            |
    | aea3d4c5-9c2e-48ae-b100-527b18d4eb02 | Test_Datastore_1 |
    | b8583e8c-8177-480e-889e-a73c5290b558 | test_ds          |
    +--------------------------------------+------------------+

Once that is done, view the image that was built for the datastore you have
kick-started and identify the resources required for it.

.. code-block:: bash

    $ openstack image list

    +--------------------------------------+--------------------------+--------+
    | ID                                   | Name                     | Status |
    +--------------------------------------+--------------------------+--------+
    | 37d4b996-14c2-4981-820e-3ac87bb4c5a2 | cirros-0.3.5-x86_64-disk | active |
    | 2d7d930a-d606-4934-8602-851207546fee | ubuntu_mysql             | active |
    +--------------------------------------+--------------------------+--------+

Grab the ID from the list and run the following command to view the size of
the image.

.. code-block:: bash

    $ openstack image show ubuntu_mysql

    +------------------+------------------------------------------------------+
    | Field            | Value                                                |
    +------------------+------------------------------------------------------+
    | checksum         | 9facdf0670ccb58ea27bf665e4fdcdf5                     |
    | container_format | bare                                                 |
    | created_at       | 2017-05-26T14:35:39Z                                 |
    | disk_format      | qcow2                                                |
    | file             | /v2/images/2d7d930a-d606-4934-8602-851207546fee/file |
    | id               | 2d7d930a-d606-4934-8602-851207546fee                 |
    | min_disk         | 0                                                    |
    | min_ram          | 0                                                    |
    | name             | ubuntu_mysql                                         |
    | owner            | e765230cd96f47f294f910551ec3c1f4                     |
    | protected        | False                                                |
    | schema           | /v2/schemas/image                                    |
    | size             | 633423872                                            |
    | status           | active                                               |
    | tags             |                                                      |
    | updated_at       | 2017-05-26T14:35:42Z                                 |
    | virtual_size     | None                                                 |
    | visibility       | public                                               |
    +------------------+------------------------------------------------------+

Take the value that says size, this is 633423872 in bytes. Cinder volumes are
in gigabytes so 633423872 becomes:

633423872 / 1024
618578 # KB
618578 / 1024
604 # MB
604 / 1024
0 # < 1 GB so we will round up.

Then test that you can create the cinder volume:

.. code-block:: bash

    $ cinder create --name my-v 1

    +--------------------------------+--------------------------------------+
    | Property                       | Value                                |
    +--------------------------------+--------------------------------------+
    | attachments                    | []                                   |
    | availability_zone              | nova                                 |
    | bootable                       | false                                |
    | consistencygroup_id            | None                                 |
    | created_at                     | 2017-05-26T16:37:55.000000           |
    | description                    | None                                 |
    | encrypted                      | False                                |
    | id                             | 7a2da60f-cc1b-4798-ba7a-1f0215c74615 |
    | metadata                       | {}                                   |
    | migration_status               | None                                 |
    | multiattach                    | False                                |
    | name                           | my-v                                 |
    | os-vol-host-attr:host          | None                                 |
    | os-vol-mig-status-attr:migstat | None                                 |
    | os-vol-mig-status-attr:name_id | None                                 |
    | os-vol-tenant-attr:tenant_id   | e765230cd96f47f294f910551ec3c1f4     |
    | replication_status             | None                                 |
    | size                           | 1                                    |
    | snapshot_id                    | None                                 |
    | source_volid                   | None                                 |
    | status                         | creating                             |
    | updated_at                     | None                                 |
    | user_id                        | cf1e59dc2e4d4aeca51aa050faac15c2     |
    | volume_type                    | lvmdriver-1                          |
    +--------------------------------+--------------------------------------+

Next, verify the cinder volume status has moved from creating to available.

.. code-block:: bash

    $ cinder show my-v

    +--------------------------------+--------------------------------------+
    | Property                       | Value                                |
    +--------------------------------+--------------------------------------+
    | attachments                    | []                                   |
    | availability_zone              | nova                                 |
    | bootable                       | false                                |
    | consistencygroup_id            | None                                 |
    | created_at                     | 2017-05-26T16:37:55.000000           |
    | description                    | None                                 |
    | encrypted                      | False                                |
    | id                             | 7a2da60f-cc1b-4798-ba7a-1f0215c74615 |
    | metadata                       | {}                                   |
    | migration_status               | None                                 |
    | multiattach                    | False                                |
    | name                           | my-v                                 |
    | os-vol-host-attr:host          | ubuntu@lvmdriver-1#lvmdriver-1       |
    | os-vol-mig-status-attr:migstat | None                                 |
    | os-vol-mig-status-attr:name_id | None                                 |
    | os-vol-tenant-attr:tenant_id   | e765230cd96f47f294f910551ec3c1f4     |
    | replication_status             | None                                 |
    | size                           | 1                                    |
    | snapshot_id                    | None                                 |
    | source_volid                   | None                                 |
    | status                         | available                            |
    | updated_at                     | 2017-05-26T16:37:56.000000           |
    | user_id                        | cf1e59dc2e4d4aeca51aa050faac15c2     |
    | volume_type                    | lvmdriver-1                          |
    +--------------------------------+--------------------------------------+

Ok, now we know that works so lets delete it.

.. code-block:: bash

    $ cinder delete my-v

Next is to choose a server flavor that fits the requirements of your datastore
and do not exceed your computer hardware limitations.

.. code-block:: bash

    $ trove flavor-list

    +------+--------------------------+--------+-------+------+-----------+
    |   ID | Name                     |    RAM | vCPUs | Disk | Ephemeral |
    +------+--------------------------+--------+-------+------+-----------+
    |    1 | m1.tiny                  |    512 |     1 |    1 |         0 |
    |   10 | test.tiny-3              |    512 |     1 |    3 |         0 |
    |  10e | test.eph.tiny-3          |    512 |     1 |    3 |         1 |
    | 10er | test.eph.tiny-3.resize   |    528 |     2 |    3 |         1 |
    |  10r | test.tiny-3.resize       |    528 |     2 |    3 |         0 |
    |   15 | test.small-3             |    768 |     1 |    3 |         0 |
    |  15e | test.eph.small-3         |    768 |     1 |    3 |         1 |
    | 15er | test.eph.small-3.resize  |    784 |     2 |    3 |         1 |
    |  15r | test.small-3.resize      |    784 |     2 |    3 |         0 |
    |   16 | test.small-4             |    768 |     1 |    4 |         0 |
    |  16e | test.eph.small-4         |    768 |     1 |    4 |         1 |
    | 16er | test.eph.small-4.resize  |    784 |     2 |    4 |         1 |
    |  16r | test.small-4.resize      |    784 |     2 |    4 |         0 |
    |   17 | test.small-5             |    768 |     1 |    5 |         0 |
    |  17e | test.eph.small-5         |    768 |     1 |    5 |         1 |
    | 17er | test.eph.small-5.resize  |    784 |     2 |    5 |         1 |
    |  17r | test.small-5.resize      |    784 |     2 |    5 |         0 |
    |    2 | m1.small                 |   2048 |     1 |   20 |         0 |
    |   20 | test.medium-4            |   1024 |     1 |    4 |         0 |
    |  20e | test.eph.medium-4        |   1024 |     1 |    4 |         1 |
    | 20er | test.eph.medium-4.resize |   1040 |     2 |    4 |         1 |
    |  20r | test.medium-4.resize     |   1040 |     2 |    4 |         0 |
    |   21 | test.medium-5            |   1024 |     1 |    5 |         0 |
    |  21e | test.eph.medium-5        |   1024 |     1 |    5 |         1 |
    | 21er | test.eph.medium-5.resize |   1040 |     2 |    5 |         1 |
    |  21r | test.medium-5.resize     |   1040 |     2 |    5 |         0 |
    |   25 | test.large-5             |   2048 |     1 |    5 |         0 |
    |  25e | test.eph.large-5         |   2048 |     1 |    5 |         1 |
    | 25er | test.eph.large-5.resize  |   2064 |     2 |    5 |         1 |
    |  25r | test.large-5.resize      |   2064 |     2 |    5 |         0 |
    |   26 | test.large-10            |   2048 |     1 |   10 |         0 |
    |  26e | test.eph.large-10        |   2048 |     1 |   10 |         1 |
    | 26er | test.eph.large-10.resize |   2064 |     2 |   10 |         1 |
    |  26r | test.large-10.resize     |   2064 |     2 |   10 |         0 |
    |   27 | test.large-15            |   2048 |     1 |   15 |         0 |
    |  27e | test.eph.large-15        |   2048 |     1 |   15 |         1 |
    | 27er | test.eph.large-15.resize |   2064 |     2 |   15 |         1 |
    |  27r | test.large-15.resize     |   2064 |     2 |   15 |         0 |
    |    3 | m1.medium                |   4096 |     2 |   40 |         0 |
    |   30 | test.fault_1-1           |    512 |     1 |    1 |         0 |
    |  30e | test.eph.fault_1-1       |    512 |     1 |    1 |         1 |
    |   31 | test.fault_2-5           | 131072 |     1 |    5 |         0 |
    |  31e | test.eph.fault_2-5       | 131072 |     1 |    5 |         1 |
    |    4 | m1.large                 |   8192 |     4 |   80 |         0 |
    |   42 | m1.nano                  |     64 |     1 |    0 |         0 |
    |  451 | m1.heat                  |    512 |     1 |    0 |         0 |
    |    5 | m1.xlarge                |  16384 |     8 |  160 |         0 |
    |   84 | m1.micro                 |    128 |     1 |    0 |         0 |
    |   c1 | cirros256                |    256 |     1 |    0 |         0 |
    |   d1 | ds512M                   |    512 |     1 |    5 |         0 |
    |   d2 | ds1G                     |   1024 |     1 |   10 |         0 |
    |   d3 | ds2G                     |   2048 |     2 |   10 |         0 |
    |   d4 | ds4G                     |   4096 |     4 |   20 |         0 |
    +------+--------------------------+--------+-------+------+-----------+


The flavor sizes are in megabytes, check your computer disk space and pick a
flavor less than your limitations.

.. code-block:: bash

    $ df -h

    Filesystem                   Size  Used Avail Use% Mounted on
    udev                         7.9G     0  7.9G   0% /dev
    tmpfs                        1.6G  162M  1.5G  11% /run
    /dev/mapper/ubuntu--vg-root   33G   11G   21G  34% /
    tmpfs                        7.9G  4.0K  7.9G   1% /dev/shm
    tmpfs                        5.0M     0  5.0M   0% /run/lock
    tmpfs                        7.9G     0  7.9G   0% /sys/fs/cgroup
    /dev/vda1                    472M  102M  346M  23% /boot
    tmpfs                        1.6G     0  1.6G   0% /run/user/1000
    /dev/loop0                   6.0G  650M  5.4G  11% /opt/stack/data/swift/drives/sdb1

I have a lot of partitions I don't understand but ubuntu--vg-root is the one
setup by LVM during the install and it is the largest one so I'm going to use 21G
as my upper limit. Now I only need 1G, this information is still good to know when
you are dealing with multiple instances, larger images, or limited disk space.

Flavors also use RAM so it's important to check your free memory.

.. code-block:: bash

    $ free -h

    total        used        free      shared  buff/cache   available
    Mem:            15G        5.1G        5.0G        150M        5.5G         10G
    Swap:           15G        4.1M         15G

I have given my VM 16GB RAM and it shows I have 5GB free. So In order to be safe,
I will choose test-small-3 (ID 15), this is RAM 768 and disk size 3GB. The disk size must be
greater than 604MB from the ubuntu_mysql image requirements, but we rounded to 1GB to
be safe.

After all of this we are ready to create our trove instance.

.. code-block:: bash

    $ trove create my-inst 15 --size 1

    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-05-26T16:53:06                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | True                                 |
    | flavor                  | 15                                   |
    | id                      | 39f8ac9e-2935-40fb-8b09-8a963fb235bd |
    | name                    | my-inst                              |
    | region                  | RegionOne                            |
    | server_id               | None                                 |
    | status                  | BUILD                                |
    | tenant_id               | e765230cd96f47f294f910551ec3c1f4     |
    | updated                 | 2017-05-26T16:53:06                  |
    | volume                  | 1                                    |
    | volume_id               | None                                 |
    +-------------------------+--------------------------------------+

Now we view the details to see if it is successful.

.. code-block:: bash

    $ trove show my-inst

    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-05-26T16:53:07                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | True                                 |
    | flavor                  | 15                                   |
    | id                      | 39f8ac9e-2935-40fb-8b09-8a963fb235bd |
    | name                    | my-inst                              |
    | region                  | RegionOne                            |
    | server_id               | 62399b7e-dec1-4606-9297-3b3711a62d68 |
    | status                  | BUILD                                |
    | tenant_id               | e765230cd96f47f294f910551ec3c1f4     |
    | updated                 | 2017-05-26T16:53:13                  |
    | volume                  | 1                                    |
    | volume_id               | da3b3951-7f7a-4c71-86b9-f0059da814f8 |
    +-------------------------+--------------------------------------+

Notice, status still says BUILD but we now have a server_id and volume_id.

After waiting a few moments, check it again.

.. code-block:: bash

    $ trove show my-inst

    +-------------------------+--------------------------------------+
    | Property                | Value                                |
    +-------------------------+--------------------------------------+
    | created                 | 2017-05-26T16:53:07                  |
    | datastore               | mysql                                |
    | datastore_version       | 5.6                                  |
    | encrypted_rpc_messaging | True                                 |
    | flavor                  | 15                                   |
    | id                      | 39f8ac9e-2935-40fb-8b09-8a963fb235bd |
    | name                    | my-inst                              |
    | region                  | RegionOne                            |
    | server_id               | 62399b7e-dec1-4606-9297-3b3711a62d68 |
    | status                  | ACTIVE                               |
    | tenant_id               | e765230cd96f47f294f910551ec3c1f4     |
    | updated                 | 2017-05-26T16:53:13                  |
    | volume                  | 1                                    |
    | volume_id               | da3b3951-7f7a-4c71-86b9-f0059da814f8 |
    | volume_used             | 0.1                                  |
    +-------------------------+--------------------------------------+

The status is now set to ACTIVE and you are done!