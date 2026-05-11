.. _install_devstack:
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

This page describes how to set up a working development environment
that can be used in deploying Trove and verifying installed components.

Config DevStack with Trove
~~~~~~~~~~~~~~~~~~~~~~~~~~

Trove can be enabled and installed in DevStack by using the plug-in
based interface it offers.

.. note::

   The following steps have been fully verified on Ubuntu 24.04

.. note::

   Make sure that you have at least 16 GB of RAM available before deploying
   DevStack with Trove, as it requires significant memory to run properly.

.. warning::

   DevStack will make substantial changes to your system during
   installation. Only run DevStack on servers or virtual machines
   that are dedicated to this purpose.

DevStack installation script should be run as a non-root user with
sudo enabled (standard logins to cloud images such as "ubuntu" or
"cloud-user" are usually fine).

If you are not using a cloud image, create a separate `stack` user
to run DevStack with

.. code-block:: console

   $ sudo useradd -s /bin/bash -d /opt/stack -m stack

.. note::

   You can create the stack user by running the ``create-stack-user.sh``
   script located in the ``devstack/tools`` directory:

Ensure home directory for the ``stack`` user has executable permission for all,
as RHEL based distros create it with ``700`` and Ubuntu 21.04+ with ``750``
which can cause issues during deployment.

.. code-block:: console

    $ sudo chmod +x /opt/stack

Since this user will be making many changes to your system, it should
have sudo privileges:

.. code-block:: console

    $ echo "stack ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/stack
    $ sudo -u stack -i

Clone the DevStack repository using a stack user (the default user
is ``ubuntu``) and change to DevStack directory:

.. code-block:: console

    git clone https://opendev.org/openstack/devstack
    cd devstack/

Create the ``local.conf`` file with the following minimal DevStack
configuration:

.. code-block:: ini

    [[local|localrc]]

    ADMIN_PASSWORD=secret
    DATABASE_PASSWORD=$ADMIN_PASSWORD
    RABBIT_PASSWORD=$ADMIN_PASSWORD
    SERVICE_PASSWORD=$ADMIN_PASSWORD

    enable_service swift
    enable_service trove
    enable_service tr-api
    enable_service tr-tmgr
    enable_service tr-cond

    # trove tempest
    enable_plugin trove https://opendev.org/openstack/trove
    enable_plugin trove-tempest-plugin https://opendev.org/openstack/trove-tempest-plugin

    # barbican service & tempest plugin
    enable_plugin barbican https://opendev.org/openstack/barbican
    enable_plugin barbican-tempest-plugin https://git.openstack.org/openstack/barbican-tempest-plugin

    # required for not interrupting install process
    SWIFT_HASH=66a3d6b56c1f479c8b4e70ab5c2000f5

Take a look at the
`options <https://opendev.org/openstack/trove/src/branch/master/devstack/settings>`_
you could use to customize the Trove installation using env variables.

Running DevStack
~~~~~~~~~~~~~~~~

To speed up test execution, it is highly recommended to enable
the ``TROVE_ENABLE_LOCAL_REGISTRY=True`` settings flag. This option
installs and uses a local container registry instead of pulling
images from ``quay.io``:

.. code-block:: console

    TROVE_ENABLE_LOCAL_REGISTRY=True ./stack.sh

The installation script downloads the required images and stores them
locally. This removes the need for internet access during test
execution and reduces the risk of hitting external registry limits.

.. note::

    Using local registry is the only way to run trove with
    ``network_isolation=True``, which is enabled by default.
    See :ref:`network isolation section <network_isolation>` for details

If you don't need local registry and network_isolation, then simply run:

.. code-block:: console

    ./stack.sh

Reinstall and cleanup
~~~~~~~~~~~~~~~~~~~~~

If installation process fails or was interrupted, you can rerun it
using commands:

.. code-block:: console

    ./unstack.sh ; ./cleanup.sh

And then run ``./stack.sh`` again.

Verify DevStack installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After a successful installation, you should have a ready-to-use
Trove DevStack environment with the following components:

    - a DEV guest image that fetches source code from
      ``/opt/stack/trove`` during database instance boot
    - preinstalled datastores: MySQL, PostgreSQL, and MariaDB
    - Tempest with ``trove-tempest-plugin`` installed and configured
    - a local registry mirror; you can verify it using
      ``curl localhost:4000/v2/_catalog`` and ``docker ps``

If something went wrong during installation, this guide can help you
identify and resolve the problem.

First, load the admin credentials:

.. code-block:: console

    cd /opt/stack
    source devstack/openrc admin admin

.. note::
    You can run
    ``echo "source /opt/stack/devstack/openrc admin admin" >> /opt/stack/.bashrc``
    to automatically load the OpenStack credentials on login.

Verify that all required endpoints are present:

.. code-block:: console

    openstack endpoint list

Example output:

.. code-block:: console

    +------+-----------+--------------+----------------+---------+-----------+--------------------------------------------------+
    | ID   | Region    | Service Name | Service Type   | Enabled | Interface | URL                                              |
    +------+-----------+--------------+----------------+---------+-----------+--------------------------------------------------+
    | <id> | RegionOne | keystone     | identity       | True    | public    | http://yourhostname/identity                    |
    | <id> | RegionOne | placement    | placement      | True    | public    | http://yourhostname/placement                   |
    | <id> | RegionOne | trove        | database       | True    | internal  | http://yourhostname:8779/v1.0/$(tenant_id)s     |
    | <id> | RegionOne | swift        | object-store   | True    | public    | http://yourhostname:8080/v1/AUTH_$(project_id)s |
    | <id> | RegionOne | glance       | image          | True    | public    | http://yourhostname/image                       |
    | <id> | RegionOne | trove        | database       | True    | admin     | http://yourhostname:8779/v1.0/$(tenant_id)s     |
    | <id> | RegionOne | nova         | compute        | True    | public    | http://yourhostname/compute/v2.1                |
    | <id> | RegionOne | neutron      | network        | True    | public    | http://yourhostname/networking                  |
    | <id> | RegionOne | swift        | object-store   | True    | admin     | http://yourhostname:8080                        |
    | <id> | RegionOne | nova_legacy  | compute_legacy | True    | public    | http://yourhostname/compute/v2/$(project_id)s   |
    | <id> | RegionOne | trove        | database       | True    | public    | http://yourhostname:8779/v1.0/$(tenant_id)s     |
    | <id> | RegionOne | cinder       | block-storage  | True    | public    | http://yourhostname/volume/v3                   |
    +------+-----------+--------------+----------------+---------+-----------+--------------------------------------------------+

.. note::

    Note that endpoinds contains ``yourhostname`` instead of ip addresses,
    this is special behavior for trove installation process only.
    Vanilla DevStack use ip addresses for endpoints by default.

Verify that Nova Compute is operational:

.. code-block:: console

    openstack host list

Example output:

.. code-block:: console

    +--------------+-----------+----------+
    | Host Name    | Service   | Zone     |
    +--------------+-----------+----------+
    | yourhostname | scheduler | internal |
    | yourhostname | conductor | internal |
    | yourhostname | compute   | nova     |
    +--------------+-----------+----------+

You can see there is a MySQL datastore available to create Trove instance:

.. code-block:: console

    $ openstack datastore version list mysql
    +--------------------------------------+------------------+
    | ID                                   | Name             |
    +--------------------------------------+------------------+
    | 9726354d-f989-4a68-9c5f-6e37b1bccc74 | 8.4              |
    +--------------------------------------+------------------+

Create your first database instance:

.. code-block:: console

    openstack database instance create --flavor d3 --datastore mysql \
        --datastore-version 8.4 --size 5 \
        --nic net-id=$(openstack network show private -c id -f value) \
        hello-world-database-instance

Example output:

.. code-block:: console

    +--------------------------+--------------------------------------+
    | Field                    | Value                                |
    +--------------------------+--------------------------------------+
    | allowed_cidrs            | []                                   |
    | created                  | 2026-03-07T10:21:20                  |
    | datastore                | mysql                                |
    | datastore_version        | 8.4                                  |
    | datastore_version_number | 8.4                                  |
    | encrypted_rpc_messaging  | True                                 |
    | flavor                   | d3                                   |
    | id                       | 4bc97953-6a65-41a2-81cf-00a09d39cbdb |
    | name                     | hello-world-database-instance        |
    | operating_status         |                                      |
    | public                   | False                                |
    | region                   | RegionOne                            |
    | server_id                | None                                 |
    | service_status_updated   | 2026-03-07T10:21:20                  |
    | status                   | BUILD                                |
    | tenant_id                | 13209b210da841e8a799cd6b3c8d27d7     |
    | updated                  | 2026-03-07T10:21:20                  |
    | volume                   | 5                                    |
    | volume_id                | None                                 |
    +--------------------------+--------------------------------------+

You can also refer to :ref:`Create and access a database <create_db>`
for the detailed info.

Verify that the corresponding Nova instance was created:

.. code-block:: console

    openstack server list --project service

Example output:

.. code-block:: console

    +-------------+-------------------------------+--------+----------------------------------------+--------------------------+--------+--------------+
    | ID          | Name                          | Status | Networks                               | Image                    | Flavor | Project ID   |
    +-------------+-------------------------------+--------+----------------------------------------+--------------------------+--------+--------------+
    | <server id> | hello-world-database-instance | ACTIVE | private=10.0.0.25,                     | trove-guest-ubuntu-noble | ds2G   | <project id> |
    |             |                               |        | fd72:8eab:73f:0:f816:3eff:fe47:1b02;   |                          |        |              |
    |             |                               |        | trove-mgmt=192.168.254.85              |                          |        |              |
    +-------------+-------------------------------+--------+----------------------------------------+--------------------------+--------+--------------+

.. note::

    The *private* network is the client network used to access the
    running database.

    The *trove-mgmt* network is an internal Trove management network
    used for communication between the Trove guest agent and the
    Trove :ref:`control plane <control_plane>`. It is also used to
    pull Docker images during database instance startup.

After a few minutes, the database instance status and operating status
should become ``ACTIVE/HEALTHY``:

.. code-block:: console

   openstack database instance list

Example output:

.. code-block:: console

    +------------------+-------------------------------+-----------+-------------------+--------+------------------+--------+-----------------------------------+-----------+------+------+
    | ID               | Name                          | Datastore | Datastore Version | Status | Operating Status | Public | Addresses                         | Flavor ID | Size | Role |
    +------------------+-------------------------------+-----------+-------------------+--------+------------------+--------+-----------------------------------+-----------+------+------+
    | <db instance id> | hello-world-database-instance | mysql     | 8.4               | ACTIVE | HEALTHY          | False  | [{'address': '10.0.0.25', 'type': | d3        |    5 |      |
    | 00a09d39cbdb     |                               |           |                   |        |                  |        | 'private', 'network': 'c11a63f2-  |           |      |      |
    |                  |                               |           |                   |        |                  |        | f928-4b3a-ad8d-e85d407f6632'}]    |           |      |      |
    +------------------+-------------------------------+-----------+-------------------+--------+------------------+--------+-----------------------------------+-----------+------+------+

If something goes wrong, you can SSH into the compute instance and
inspect the logs:

.. code-block:: console

   ssh ubuntu@192.168.254.85
   less /var/log/trove/guest-agent.log

.. note::

    In production deployments of Trove, cloud administrators can also
    SSH into the instance from a compute node using the management
    network and the Trove SSH key.

What's next?
~~~~~~~~~~~~

If you plan to contribute into Trove, you can take a look at
:ref:`contributing section <contribute>` or
:ref:`Hints for developers section <hints_for_developers>`