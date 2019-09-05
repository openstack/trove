.. _install-manual:

Manual Trove Installation
=========================

Objectives
~~~~~~~~~~

This document provides a step-by-step guide for manual installation of Trove
with an existing OpenStack environment for development purposes.

This document will not cover OpenStack setup for other services.

Requirements
~~~~~~~~~~~~

A running OpenStack environment installed on Ubuntu 16.04 or 18.04 LTS is
required, including the following components:

- Compute (Nova)
- Image Service (Glance)
- Identity (Keystone)
- Network (Neutron)
- If you want to provision databases on block-storage volumes, you also need
  Block Storage (Cinder)
- If you want to do backup/restore or replication, you also need Object Storage
  (Swift)
- AMQP service (RabbitMQ or QPID)
- MySQL (SQLite, PostgreSQL) database

Networking requirements
-----------------------

Trove makes use of an "Management Network" that the controller uses to talk to
trove instance and vice versa. All the trove instance that Trove deploys will
have interfaces and IP addresses on this network. Therefore, it’s important
that the subnet deployed on this network be sufficiently large to allow for the
maximum number of trove instance and controllers likely to be deployed
throughout the lifespan of the cloud installation.

You must also create a Neutron security group which will be applied to trove
instance port created on the management network. The cloud admin has full
control of the security group, e.g it can be helpful to allow SSH access to the
trove instance from the controller for troubleshooting purposes (ie. TCP port
22), though this is not strictly necessary in production environments.

Finally, you need to add routing or interfaces to this network so that the
Trove controller is able to communicate with Nova servers on this network.

Trove Installation
~~~~~~~~~~~~~~~~~~

Required packages for Trove
---------------------------

List of packages to be installed:

.. code-block:: bash

    $ sudo apt-get install -y build-essential python-dev libpython-dev \
    python-setuptools libffi-dev libxslt1-dev libxml2-dev libyaml-dev \
    libssl-dev zlib1g-dev mysql-client python-pymysql libmysqlclient-dev git

Python settings
---------------

Install pip:

.. code-block:: bash

    curl -SO# https://bootstrap.pypa.io/get-pip.py && sudo python get-pip.py pip==9.0.3 && rm -f get-pip.py

Install virtualenv, create Trove environment and activate it:

.. code-block:: bash

    pip install virtualenv --user
    virtualenv --system-site-packages trove_env
    source trove_env/bin/activate

Get Trove
---------

Obtain the Trove source components from OpenStack repositories:

.. code-block:: bash

    cd ~
    git clone https://opendev.org/openstack/trove.git
    git clone https://opendev.org/openstack/python-troveclient.git


Install Trove
-------------

First, install the requirements:

.. code-block:: bash

    cd ~/trove
    sudo pip install -r requirements.txt -r test-requirements.txt

Then, install Trove:

.. code-block:: bash

    sudo pip install -e .

Finally, install the Trove client:

.. code-block:: bash

    cd ~/python-troveclient
    sudo pip install -e .
    cd ~

Other required OpenStack clients (python-novaclient, python-keystoneclient,
etc.) should already be installed as part of the Trove requirements.

Prepare Trove for OpenStack
---------------------------

.. note::

    You need to run the following commands using OpenStack admin credentials.

#.  Create Trove service user with admin role in the ``service`` project.

    .. code-block:: bash

        openstack user create trove --project service --password-prompt
        openstack role add --user trove --project service admin

#.  Register Trove in Keystone.

    .. code-block:: bash

        openstack service create --name trove --description "Database" database
        openstack endpoint create --region RegionOne database public 'http://<EnvironmentPublicIP>:8779/v1.0/$(tenant_id)s'
        openstack endpoint create --region RegionOne database admin 'http://<EnvironmentPublicIP>:8779/v1.0/$(tenant_id)s'
        openstack endpoint create --region RegionOne database internal 'http://<EnvironmentPublicIP>:8779/v1.0/$(tenant_id)s'

    Where <EnvironmentPublicIP> is the IP address of the server where Trove was
    installed. This IP should be reachable from any hosts that will be used to
    communicate with Trove.

Trove configuration
~~~~~~~~~~~~~~~~~~~

There are several configuration files for Trove, you can find samples of the
config files in ``etc/trove/`` of Trove repo:

- api-paste.ini and trove.conf — For trove-api service
- trove-guestagent.conf — For trove-guestagent service
- ``<datastore_manager>.cloudinit`` — Userdata for VMs during provisioning

Options in trove.conf
---------------------

#.  Config service tenant model, change the values according to your own
    environment.

    .. code-block:: ini

        nova_proxy_admin_user = admin
        nova_proxy_admin_pass = password
        nova_proxy_admin_tenant_name = admin
        nova_proxy_admin_tenant_id = f472127c03f6410899225e26a3c1d22c
        nova_proxy_admin_user_domain_name = default
        nova_proxy_admin_project_domain_name = default
        remote_nova_client = trove.common.single_tenant_remote.nova_client_trove_admin
        remote_cinder_client = trove.common.single_tenant_remote.cinder_client_trove_admin
        remote_neutron_client = trove.common.single_tenant_remote.neutron_client_trove_admin
        os_region_name = RegionOne

#.  Management config options.

    management_networks
      Trove management network ID list. Cloud admin needs to create the
      networks.

    management_security_groups
      Security group IDs that applied to the management port in the trove
      instance. Cloud admin needs to create the security groups.

    nova_keypair
      The Nova keypair used to create trove instance. Cloud admin needs to
      create the keypair.

    cinder_volume_type
      The Cinder volume type name used to create volume that attached to the
      trove instance, otherwise, users need to provide the volume type when
      creating the instance.

Prepare Trove database
~~~~~~~~~~~~~~~~~~~~~~

Create the Trove database schema:

- Connect to the storage backend (MySQL, PostgreSQL)
- Create a database called `trove` (this database will be used for storing
  Trove ORM)
- Compose connection string. Example:
  ``mysql+pymysql://<user>:<password>@<backend_host>:<backend_port>/<database_name>``

Initialize the database
-----------------------

Once the database for Trove is created, its structure needs to be populated.

.. code-block:: bash

    $ trove-manage db_sync

Create and register Trove guest image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To build Trove guest image, refer to
`Build guest agent image <https://docs.openstack.org/trove/latest/admin/trovestack.html#build-guest-agent-image>`_

Run Trove
~~~~~~~~~

Starting Trove services
-----------------------

Run trove-api:

.. code-block:: bash

    $ trove-api --config-file=${TROVE_CONF_DIR}/trove.conf &

Run trove-taskmanager:

.. code-block:: bash

    $ trove-taskmanager --config-file=${TROVE_CONF_DIR}/trove.conf &

Run trove-conductor:

.. code-block:: bash

   $ trove-conductor --config-file=${TROVE_CONF_DIR}/trove.conf &
