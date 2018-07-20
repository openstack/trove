.. _manual_install:

=========================
Manual Trove Installation
=========================

Objectives
==========

This document provides a step-by-step guide for manual installation of Trove with
an existing OpenStack environment for development purposes.

This document will not cover:

- OpenStack setup
- Trove service configuration

Requirements
============

A running OpenStack environment is required, including the following components:

- Compute (Nova)
- Image Service (Glance)
- Identity (Keystone)
- Network (Neutron)
- If you want to provision datastores on block-storage volumes, you also will need Block Storage (Cinder)
- If you want to do backup/restore and replication, you will also need Object Storage (Swift)
- An environment with a freshly installed Ubuntu 16.04 LTS to run Trove services.
  This will be referred to as "local environment"
- AMQP service (RabbitMQ or QPID)
- MySQL (SQLite, PostgreSQL) database for Trove's internal needs, accessible from the local environment
- Certain OpenStack services must be accessible from VMs:
    - Swift

- VMs must be accessible from local environment for development/debugging purposes

- OpenStack services must be accessible directly from the local environment, such as:
    - Nova
    - Cinder
    - Swift
    - Heat

Installation
============

-----------
Gather info
-----------

The following information about the existing environment is required:

- Keystone host and port(s)
- OpenStack administrator's username, tenant name and password
- Nova URL
- Cinder URL
- Swift URL
- Heat URL
- AMQP connection credentials (server URL, user, password)
- Trove's controller backend connection string (MySQL, SQLite, PostgreSQL)

--------------------
Install dependencies
--------------------

Required packages for Trove
---------------------------

List of packages to be installed:

.. code-block:: bash

   $ sudo apt-get install build-essential libxslt1-dev qemu-utils mysql-client \
     git python-dev python-pexpect python-pymysql libmysqlclient-dev

Python settings
---------------

To find out which setuptools version is latest please check out the `setuptools repo`_.

.. _setuptools repo: https://pypi.org/project/setuptools/

To find out which pip version is latest please visit the `pip repo`_.

.. _pip repo: https://pypi.org/project/pip/

Some packages in Ubuntu repositories are outdated. Please make sure to update to the latest versions from the appropriate sources.

Use latest setuptools:

Go https://pypi.org/project/setuptools, download the latest source setuptools, and move it under ~

.. code-block:: bash

    $ cd ~
    $ tar xfvz setuptools-{{latest}}.tar.gz
    $ cd setuptools-{{latest}}
    $ python setup.py install --user

Use latest pip:

Go https://pypi.org/project/pip, download the latest source pip, and move it under ~

.. code-block:: bash

    $ tar xfvz pip-{{latest}}.tar.gz
    $ cd pip-{{latest}}
    $ python setup.py install --user

Note '--user' above -- we installed packages in user's home dir, in $HOME/.local/bin, so we need to add it to path:

.. code-block:: bash

    $ echo PATH="$HOME/.local/bin:$PATH" >> ~/.profile
    $ . ~/.profile

Install virtualenv, create environment and activate it:

.. code-block:: bash

    $ pip install virtualenv --user
    $ virtualenv --system-site-packages env
    $ . env/bin/activate

Get Trove
---------

Obtain the Trove source components from OpenStack repositories:

.. code-block:: bash

    $ cd ~
    $ git clone https://git.openstack.org/openstack/trove.git
    $ git clone https://git.openstack.org/openstack/python-troveclient.git


Install Trove
=============

First, install the requirements:

.. code-block:: bash

    $ cd ~/trove
    $ pip install -r requirements.txt -r test-requirements.txt

Then, install Trove:

.. code-block:: bash

    $ sudo python setup.py develop

Finally, install the Trove client:

.. code-block:: bash

    $ cd ~/python-troveclient
    $ sudo python setup.py develop
    $ cd ~

Other required OpenStack clients (python-novaclient, python-keystoneclient, etc.) should already be installed as part of the Trove requirements.


---------------------------
Prepare Trove for OpenStack
---------------------------

You will first need to create a tenant called 'trove_for_trove_usage'.
Next, create users called 'regular_trove_user' and 'admin_trove_user' —using 'trove' as the password. These are the accounts used by the Trove service.
Additionally, you will need to register Trove as an OpenStack service and its endpoints:

.. code-block:: bash

    $ keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword> --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIP>:<KeystonePort>/v2.0 tenant-create --user trove_for_trove_usage

    $ keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword> --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIP>:<KeystonePort>/v2.0 user-create --user regular_trove_user --pass trove --tenant trove_for_trove_usage

    $ keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword> --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIP>:<KeystonePort>/v2.0 user-create --user admin_trove_user --pass trove --tenant trove_for_trove_usage

    $ keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword> --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIP>:<KeystonePort>/v2.0 user-role-add --user admin_trove_user --tenant trove_for_trove_usage --role admin

    $ keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword> --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIP>:<KeystonePort>/v2.0 service-create --user trove --type database

    $ keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword> --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIP>:<KeystonePort>/v2.0 endpoint-create --service trove --region RegionOne --publicurl 'http://<EnvironmentPublicIP>:<EnvironmentPort>/v1.0/$(tenant_id)s' --adminurl 'http://<EnvironmentPublicIP>:<EnvironmentPort>/v1.0/$(tenant_id)s' --internalurl 'http://<EnvironmentPublicIP>:<EnvironmentPort>/v1.0/$(tenant_id)s'

Where <EnvironmentPublicIP> and <EnvironmentPort> are the IP address and Port of the server where Trove was installed. This IP should be reachable from any hosts that will be used to communicate with Trove.

Prepare Trove configuration files
=================================

There are several configuration files for Trove:

- api-paste.ini and trove.conf — For trove-api service
- trove-taskmanager.conf — For trove-taskmanager service
- trove-guestagent.conf — For trove-guestagent service
- trove-conductor.conf — For trove-conductor service
- <datastore_manager>.cloudinit — Userdata for VMs during provisioning

Cloud-init scripts are userdata that is being used for different datastore types like mysql/percona, cassandra, mongodb, redis, couchbase while provisioning new compute instances.

Samples of the above are available in ~/trove/etc/trove/ as \*.conf.sample files.

If a clean Ubuntu image is used as the source image for Trove instances, the cloud-init script must install and run guestagent in the instance.

As an alternative, one may consider creating a custom image with pre-installed and pre-configured Trove in it.

Source images
=============

As the source image for Trove instances, we will use a Trove-compatible Ubuntu image:

.. code-block:: bash

    $ export DATASTORE_TYPE="mysql"
    $ wget http://tarballs.openstack.org/trove/images/ubuntu/${DATASTORE_TYPE}.qcow2
    $ glance --os-username admin_trove_user --os-password trove --os-tenant-name trove_for_trove_usage --os-auth-url http://<KeystoneIP>:<KeystoneAdminPort>/v2.0 image-create --name trove-image --is-public True --container-format ovf --disk-format qcow2 --file ${DATASTORE_TYPE}.qcow2

Note: http://tarballs.openstack.org/trove/images includes mysql, percona, mongodb Trove-compatible images.

At this step please remember the image ID or store it in an environment variable (IMAGEID).

.. code-block:: bash

    $ glance --os-username trove --os-password trove --os-tenant-name trove --os-auth-url http://<KeystoneIP>:<KeystoneAdminPort>/v2.0
        image-create --name trove-image --is-public true --container-format ovf --disk-format qcow2 --owner trove < precise.qcow2

    $ export IMAGEID=<glance_image_id>


Cloud-init scripts
==================

-------------------
Cloud-init location
-------------------

By default, trove-taskmanager will look at /etc/trove/cloudinit for <datastore_manager>.cloudinit.

------------------
Cloud-init content
------------------

Each cloud-init script for Trove-compatible images should contain:

- Trove installation

Custom images with Trove code inside
====================================

*To be added*

Prepare the database
====================

Create the Trove database schema:

- Connect to the storage backend (MySQL, PostgreSQL)
- Create a database called `trove` (this database will be used for storing Trove ORM)
- Compose connection string. Example: mysql+pymysql://<user>:<password>@<backend_host>:<backend_port>/<database_name>

Initialize the database
=======================

Once the database for Trove is created, its structure needs to be populated.

.. code-block:: bash

    $ trove-manage db_sync

Setup Trove Datastores
======================

---------
Datastore
---------

A Datastore is a data structure that describes a set of Datastore Versions, which consists of::

    - ID -- simple auto-generated UUID
    - Name -- user-defined attribute, actual name of a datastore
    - Datastore Versions


Example::

  - mysql, cassandra, redis, etc.

-----------------
Datastore Version
-----------------

A Datastore Version is a data structure that describes a version of a specific database pinned to datastore, which consists of::

    - ID — Simple auto-generated UUID
    - Datastore ID — Reference to Datastore
    - Name — User-defined attribute, actual name of a database version
    - Datastore manager — trove-guestagent manager that is used for datastore management
    - Image ID — Reference to a specific Glance image ID
    - Packages — Operating system specific packages that would be deployed onto datastore VM
    - Active — Boolean flag that defines if version can be used for instance deployment or not

Example::

  - ID - edb1d22a-b66d-4e86-be60-756240439272
  - Datastore ID - 9c3d890b-a2f2-4ba5-91b2-2997d0791502
  - Name - mysql-5.7
  - Datastore manager - mysql
  - Image ID - d73a402-3953-4721-8c99-86fc72e1cb51
  - Packages - mysql-server=5.7, percona-xtrabackup=2.4
  - Active - True

--------------------------------------------
Datastore and Datastore Version registration
--------------------------------------------

To register a datastore, you must execute:

.. code-block:: bash

    $ export DATASTORE_TYPE="mysql" # available options: mysql, mongodb, postgresql, redis, cassandra, couchbase, couchdb, db2, vertica, etc.

    $ export DATASTORE_VERSION="5.7" # available options: for cassandra 2.0.x, for mysql: 5.x, for mongodb: 2.x.x, etc.

    $ export PACKAGES="mysql-server-5.7" # available options: cassandra=2.0.9, mongodb=2.0.4, etc

    $ export IMAGEID="9910350b-77e3-4790-86be-b971d0cf9175" # Glance image ID of the relevant Datastore version (see Source images section)

    $ trove-manage datastore_update ${DATASTORE_TYPE} ""

    $ trove-manage datastore_version_update ${DATASTORE_TYPE} ${DATASTORE_VERSION} ${DATASTORE_TYPE} ${IMAGEID} ${PACKAGES} 1

    $ trove-manage datastore_update ${DATASTORE_TYPE} ${DATASTORE_VERSION}

=========
Run Trove
=========

Trove services configuration and tuning
=======================================

*To be added*

Starting Trove services
=======================

Run trove-api:

.. code-block:: bash

    $ trove-api --config-file=${TROVE_CONF_DIR}/trove-api.conf &

Run trove-taskmanager:

.. code-block:: bash

    $ trove-taskmanager --config-file=${TROVE_CONF_DIR}/trove-taskamanger.conf &

Run trove-conductor:

.. code-block:: bash

   $ trove-conductor --config-file=${TROVE_CONF_DIR}/trove-conductor.conf &

=================
Trove interaction
=================

Keystonerc
==========

You need to build a `keystonerc` file that contains data to simplify the auth processes while using the Trove client:

.. code-block:: bash

        export OS_TENANT_NAME=trove

        export OS_USERNAME=regular_trove_user

        export OS_PASSWORD=trove

        export OS_AUTH_URL="http://<KeystoneIP>:<KeystonePort>/v2.0/"

        export OS_AUTH_STRATEGY=keystone

Trove deployment verification
=============================

First you need to execute:

.. code-block:: bash

    $ . keystonerc

To see `help` for a specific command:

.. code-block:: bash

    $ trove help <command>

To create an instance:

.. code-block:: bash

    $ trove create <name> <flavor_id>
                    [--size <size>]
                    [--databases <databases> [<databases> ...]]
                    [--users <users> [<users> ...]] [--backup <backup>]
                    [--availability_zone <availability_zone>]
                    [--datastore <datastore>]
                    [--datastore_version <datastore_version>]
                    [--nic <net-id=net-uuid,v4-fixed-ip=ip-addr,port-id=port-uuid>]
                    [--configuration <configuration>]
                    [--replica_of <source_id>]

===============
Troubleshooting
===============

No instance IPs in the output of 'trove show <instance_id>'
===========================================================

If the Trove instance was successfully created, is showing ACTIVE state and working, yet there is no IP address for the instance shown in the output of 'trove show <instance_id>, then confirm the following lines are added to trove.conf ::

    network_label_regex = ^NETWORK_NAME$

where NETWORK_NAME should be replaced with real name of the network to which the instance is connected to.

To decide which network would you like to attach a Trove instance to, run the following command:

.. code-block:: bash

   $ openstack network list

One possible way to find the network name is to execute the 'nova list' command. The output will list all OpenStack instances for the tenant, including network information. Look for ::

    NETWORK_NAME=IP_ADDRESS


Additional information
======================

Additional information can be found in the OpenStack installation guide for the trove project. This document can be found under the "Installation Tutorials and Guides" section of the OpenStack Documentation.

For the current documentation, visit:

http://docs.openstack.org/index.html#install-guides

Select the link for "Installation Tutorials and Guides"

The installation guides for trove (the Database Service) can be found under the appropriate operating system.

If you are interested in documentation for a specific OpenStack release, visit:

http://docs.openstack.org/<release-code-name>/

For example, the documentation for the Pike release is found at:

http://docs.openstack.org/pike/

and the documentation for the Queens release is found at:

http://docs.openstack.org/queens/
