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

    enable_plugin trove https://opendev.org/openstack/trove

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

Refer to
`Create and access a database <https://docs.openstack.org/trove/latest/user/create-db.html>`_
for the detailed steps.