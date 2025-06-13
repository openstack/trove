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
environment that can be used in deploying Trove.

Config DevStack with Trove
~~~~~~~~~~~~~~~~~~~~~~~~~~

Trove can be enabled and installed in DevStack by using the plug-in
based interface it offers.

.. note::

   The following steps have been fully verified both on Ubuntu 22.04/24.04
   and Rocky Linux 9.

.. note::

   Make sure that you have at least 16 GB of RAM available before deploying
   DevStack with Trove, as it requires significant memory to run properly.

DevStack should be run as a non-root user with sudo enabled
(standard logins to cloud images such as "ubuntu" or "cloud-user"
are usually fine).

Clone the DevStack repository using a stack user (the default user
is ``ubuntu``) and change to DevStack directory:

.. code-block:: console

    git clone https://opendev.org/openstack/devstack
    cd devstack/

.. note::

   You can create the stack user by running the ``create-stack-user.sh``
   script located in the ``devstack/tools`` directory:

If you are not using a cloud image, create a separate `stack` user
to run DevStack with

.. code-block:: console

   $ sudo useradd -s /bin/bash -d /opt/stack -m stack

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

Create the ``local.conf`` file with the following minimal DevStack
configuration, change the ``HOST_IP`` to your own DevStack host IP address:

.. code-block:: ini

    [[local|localrc]]
    RECLONE=False
    HOST_IP=<your-host-ip-here>

    enable_plugin trove https://opendev.org/openstack/trove
    enable_plugin trove-dashboard https://opendev.org/openstack/trove-dashboard

    LIBS_FROM_GIT+=,python-troveclient
    ADMIN_PASSWORD=password
    DATABASE_PASSWORD=$ADMIN_PASSWORD
    SERVICE_PASSWORD=$ADMIN_PASSWORD
    SERVICE_TOKEN=$ADMIN_PASSWORD
    RABBIT_PASSWORD=$ADMIN_PASSWORD
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

    # Horizon
    enable_service horizon

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

    Q_AGENT=ovn
    Q_ML2_PLUGIN_MECHANISM_DRIVERS=ovn,logger
    Q_ML2_PLUGIN_TYPE_DRIVERS=local,flat,vlan,geneve
    Q_ML2_TENANT_NETWORK_TYPE="geneve"
    enable_service ovn-northd
    enable_service ovn-controller
    enable_service q-ovn-metadata-agent

    # Neutron
    enable_service q-svc

    # Disable Neutron agents not used with OVN.
    disable_service q-agt
    disable_service q-l3
    disable_service q-dhcp
    disable_service q-meta

    # Enable services, these services depend on neutron plugin.
    enable_plugin neutron https://opendev.org/openstack/neutron
    enable_service q-trunk
    enable_service q-dns
    enable_service q-port-forwarding
    enable_service q-qos
    enable_service neutron-segments
    enable_service q-log

    # Enable neutron tempest plugin tests
    enable_plugin neutron-tempest-plugin https://opendev.org/openstack/neutron-tempest-plugin
    OVN_BUILD_MODULES=True
    ENABLE_CHASSIS_AS_GW=True

    # Swift
    ENABLED_SERVICES+=,swift
    SWIFT_HASH=66a3d6b56c1f479c8b4e70ab5c2000f5
    SWIFT_REPLICAS=1
    SWIFT_MAX_FILE_SIZE=5368709122

Take a look at the
`options <https://opendev.org/openstack/trove/src/branch/master/devstack/settings>`_
you could use to customize the Trove installation.

Running DevStack
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

Refer to
`Create and access a database <https://docs.openstack.org/trove/latest/user/create-db.html>`_
for the detailed steps.
