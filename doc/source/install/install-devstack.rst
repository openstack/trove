..
      Copyright 2019 Catalyst Cloud
      All Rights Reserved.
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Install Trove in DevStack
=========================

This page describes how to set up a working development
environment that can be used in deploying Trove on latest releases
of Ubuntu.

Following these instructions will allow you to have a fully functional Trove
environment using the DevStack on Ubuntu 16.04 or 18.04.

Config DevStack with Trove
~~~~~~~~~~~~~~~~~~~~~~~~~~

Trove can be enabled in devstack by using the plug-in based interface it
offers.

.. note::

   The following steps have been fully verified both on Ubuntu 16.04 and 18.04.

Start by cloning the devstack repository using a non-root user(the default user
is ``ubuntu``) and change to devstack directory:

.. code-block:: console

    git clone https://opendev.org/openstack/devstack
    cd devstack/

Create the ``local.conf`` file with the following minimal devstack
configuration, change the ``HOST_IP`` to your own devstack host IP address:

.. code-block:: ini

    [[local|localrc]]
    RECLONE=False
    HOST_IP=<your-host-ip-here>

    enable_plugin trove https:/opendev.org/openstack/trove

    LIBS_FROM_GIT+=,python-troveclient
    DATABASE_PASSWORD=password
    ADMIN_PASSWORD=password
    SERVICE_PASSWORD=password
    SERVICE_TOKEN=password
    RABBIT_PASSWORD=password
    LOGFILE=$DEST/logs/stack.sh.log
    VERBOSE=True
    LOG_COLOR=False
    LOGDAYS=1

    IPV4_ADDRS_SAFE_TO_USE=10.111.0.0/26
    FIXED_RANGE=10.111.0.0/26
    NETWORK_GATEWAY=10.111.0.1
    FLOATING_RANGE=172.30.5.0/24
    PUBLIC_NETWORK_GATEWAY=172.30.5.1

    # Pre-requisites
    ENABLED_SERVICES=rabbit,mysql,key

    # Nova
    enable_service n-api
    enable_service n-cpu
    enable_service n-cond
    enable_service n-sch
    enable_service n-api-meta
    enable_service placement-api
    enable_service placement-client

    # Glance
    enable_service g-api
    enable_service g-reg

    # Cinder
    enable_service cinder
    enable_service c-api
    enable_service c-vol
    enable_service c-sch

    # Neutron
    enable_service q-svc
    enable_service q-agt
    enable_service q-dhcp
    enable_service q-l3
    enable_service q-meta

    # enable DVR
    Q_PLUGIN=ml2
    Q_ML2_TENANT_NETWORK_TYPE=vxlan
    Q_DVR_MODE=legacy

    # Swift
    ENABLED_SERVICES+=,swift
    SWIFT_HASH=66a3d6b56c1f479c8b4e70ab5c2000f5
    SWIFT_REPLICAS=1

    # Trove
    TROVE_DISABLE_IMAGE_SETUP=False

Take a look at the
`options <https://opendev.org/openstack/trove/src/branch/master/devstack/settings>`_
you could use to customize the Trove installation.

Running devstack
~~~~~~~~~~~~~~~~

Run the ``stack.sh`` script:

.. code-block:: console

    ./stack.sh

After it completes, you can see there is a MySQL datastore available to create
Trove instance:

.. code-block:: console

    $ openstack datastore version list mysql
    +--------------------------------------+------------------+
    | ID                                   | Name             |
    +--------------------------------------+------------------+
    | 9726354d-f989-4a68-9c5f-6e37b1bccc74 | 5.7              |
    | f81a8448-2f6e-4746-8d97-866ab7dcccee | inactive_version |
    +--------------------------------------+------------------+

Create your first Trove instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#.  Switch to a non-admin user, choose a Nova flavor ID for the Trove
    instance.

    .. code-block:: console

        $ source ~/devstack/openrc demo demo
        $ openstack flavor list
        +----+---------------+-------+------+-----------+-------+-----------+
        | ID | Name          |   RAM | Disk | Ephemeral | VCPUs | Is Public |
        +----+---------------+-------+------+-----------+-------+-----------+
        | 1  | m1.tiny       |   512 |    1 |         0 |     1 | True      |
        | 2  | m1.small      |  2048 |   20 |         0 |     1 | True      |
        | 3  | m1.medium     |  4096 |   40 |         0 |     2 | True      |
        | 4  | m1.large      |  8192 |   80 |         0 |     4 | True      |
        | 5  | m1.xlarge     | 16384 |  160 |         0 |     8 | True      |
        | 6  | mysql-minimum |   512 |    5 |         0 |     1 | True      |
        | c1 | cirros256     |   256 |    1 |         0 |     1 | True      |
        | d1 | ds512M        |   512 |    5 |         0 |     1 | True      |
        | d2 | ds1G          |  1024 |   10 |         0 |     1 | True      |
        | d3 | ds2G          |  2048 |   10 |         0 |     2 | True      |
        | d4 | ds4G          |  4096 |   20 |         0 |     4 | True      |
        +----+---------------+-------+------+-----------+-------+-----------+
        $ flavorid=6

#.  Choose a private network on which the database service can be accessed.

    .. code-block:: console

        $ openstack network list --internal
        +--------------------------------------+---------+----------------------------------------------------------------------------+
        | ID                                   | Name    | Subnets                                                                    |
        +--------------------------------------+---------+----------------------------------------------------------------------------+
        | a0f3cf12-3562-4064-aa34-61d37265e867 | private | 377e791f-2631-4d8e-93cd-036344b24b3f, 7e04abb4-7c16-4b92-8865-7831ecf3ee66 |
        +--------------------------------------+---------+----------------------------------------------------------------------------+
        # netid=a0f3cf12-3562-4064-aa34-61d37265e867

#.  Create the Trove instance.

    .. code-block:: console

        $ openstack database instance create my-first-trove-instance $flavorid \
          --size 1 \
          --nic net-id=$netid \
          --datastore mysql --datastore_version 5.7 \
          --databases test --users test_user:password