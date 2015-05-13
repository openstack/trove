.. _manual_install:

=========================
Manual Trove Installation
=========================

Objectives
==========

This document is aimed to provide a step-by-step guide for manual installation of Trove with an existing OpenStack
environment for development purposes.

This document does not cover OpenStack setup.

This document does not cover production-specific moments like high availability or security.

This document does not cover all possible configurations. It only provides one possible way to get things
running.

Requirements
============

- PC with freshly installed Ubuntu 12.04 to run Trove services. This will be referred to as "local PC"

- Running OpenStack environment that includes at least the following components:

  - Compute (nova)
  - Image Service (glance)
  - Identity (keystone)
  - A networking component (either neutron or nova-network)
  - If you want to provision datastores on block-storage volumes, you also need Block Storage (cinder)
  - If you want to do backup and restore, you also need Object Storage (swift)

- AMQP service provided by RabbitMQ

- MySQL database for Trove's internal needs, accessible from the local PC

- Though it is not required by OpenStack itself, all OpenStack services must be accessible via network from virtual machines

- Trove's database must be accessible from VMs, i.e. one must be able to connect to DB from VM

- VMs must be accessible from local PC (same network)

Installation
============

-----------
Gather info
-----------

..
    TODO: Requirements below (e.g. admin credentials) are obviously excessive. Try to use regular account.

The following information about existing environment is required:

- Keystone host and port(s)

- OpenStack administrator's username, tenant and password

- Nova compute URL

- Cinder URL

- Swift URL

- RabbitMQ URL, user Id, password

- Trove's MySQL connection string

--------------------
Install dependencies
--------------------
* Install required packages::

    # sudo apt-get install build-essential libxslt1-dev qemu-utils mysql-client git python-dev python-pexpect python-mysqldb libmysqlclient-dev

* Some packages in Ubuntu repo are outdated, so install their latest version from sources::

    # cd ~
    # wget https://pypi.python.org/packages/source/s/setuptools/setuptools-0.9.8.tar.gz
    # tar xfvz setuptools-0.9.8.tar.gz
    # cd setuptools-0.9.8
    # python setup.py install --user

    # cd ~
    # wget https://pypi.python.org/packages/source/p/pip/pip-1.4.1.tar.gz
    # tar xfvz pip-1.4.1.tar.gz
    # cd pip-1.4.1
    # python setup.py install --user

    # cd ~

* Note '--user' above -- we installed packages in user's home dir, in $HOME/.local/bin, so we need to add it to path::

    # echo PATH="$HOME/.local/bin:$PATH" >> ~/.profile
    # . ~/.profile

* Install virtualenv, create environment and activate it::

    # pip install virtualenv --user
    # virtualenv --system-site-packages env
    # . env/bin/activate


------------
Obtain Trove
------------
* Get Trove's sources from git::

    # git clone https://git.openstack.org/openstack/trove.git
    # git clone https://git.openstack.org/openstack/python-troveclient.git

-------------
Install Trove
-------------
* First install required python packages::

    # cd ~/trove
    # pip install -r requirements.txt

* Resolve dependency conflicts (if there are any)

Trove is being built and tested against latest versions of OpenStack components that can be obtained from git.
But setup downloads dependencies from PyPI which may contain outdated versions. This may cause a dependency conflicts.
E.g. for now python-cinderclient from PyPI requires older 'requests' than one installed by default, so fix it manually::

    # pip install --upgrade 'requests<1.2.3'

or consider manual installing fresh OpenStack components from git

* Install Trove itself::

    # python setup.py develop

* Install Trove CLI::

    # cd ~/python-troveclient
    # python setup.py develop
    # cd ~

* We'll need glance client as well::

    # pip install python-glanceclient

-----------------
Prepare OpenStack
-----------------
* Create a tenant 'trove' and user 'trove' with password 'trove' to be used with Trove.

These values are not required to all be 'trove'; you can instead choose your own values for the name,
tenant, and password::

    # keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword>
        --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIp>:35357/v2.0
        tenant-create --name trove

    # keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword>
        --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIp>:35357/v2.0
        user-create --name trove --pass trove --tenant trove

    # keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword>
        --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIp>:35357/v2.0
        user-role-add --name trove --tenant trove --role admin

* Create service for trove::

    # keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword>
        --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIp>:35357/v2.0
        service-create --name trove --type database

* Create an endpoint that points to localhost. Pay attention to the use of quotes (')::

    # keystone --os-username <OpenStackAdminUsername> --os-password <OpenStackAdminPassword>
        --os-tenant-name <OpenStackAdminTenant> --os-auth-url http://<KeystoneIp>:35357/v2.0
        endpoint-create --service trove --region RegionOne
        --publicurl 'http://localhost:8779/v1.0/$(tenant_id)s'
        --adminurl 'http://localhost:8779/v1.0/$(tenant_id)s'
        --internalurl 'http://localhost:8779/v1.0/$(tenant_id)s'

---------------------------------
Prepare Trove configuration files
---------------------------------

There are several configuration files for Trove:

- api-paste.ini and trove.conf -- for trove-api

- trove-taskmanager.conf -- for trove-taskmanager

- trove-guestagent.conf -- for trove-guestagent

- <service_type>.cloudinit -- cloudinit scripts for different service types. For now only 'mysql' and 'percona' are recognized as valid service types. NOTE: file names must exactly follow the pattern, e.g. 'mysql.cloudinit'

Samples of the above are available in $TROVE/trove/etc/trove/ as \*.conf.sample files.

If a vanilla Ubuntu image used as a source image for Trove instances, then it is cloudinit script's responsibility
to install and run Trove guestagent in the instance.

As an alternative one may consider creating a custom image with pre-installed and pre-configured Trove in it.

-------------
Prepare image
-------------
* As the source image for trove instances, we will use a cloudinit-enabled vanilla Ubuntu image::

    # wget http://cloud-images.ubuntu.com/precise/current/precise-server-cloudimg-amd64-disk1.img

* Convert the downloaded image into uncompressed qcow2::

    # qemu-img convert -O qcow2 precise-server-cloudimg-amd64-disk1.img precise.qcow2

* Upload the converted image into Glance::

    # glance --os-username trove --os-password trove --os-tenant-name trove --os-auth-url http://<KeystoneIp>:35357/v2.0
        image-create --name trove-image --is-public true --container-format ovf --disk-format qcow2 --owner trove < precise.qcow2

----------------
Prepare database
----------------
* Initialize the database::

    # trove-manage --config-file=<PathToTroveConf> db_recreate trove_test.sqlite mysql fake

* Setup trove to use the uploaded image. Enter the following in a single line, note quotes (') and backquotes(`)::

    # trove-manage --config-file=<PathToTroveConf> image_update mysql
        `nova --os-username trove --os-password trove --os-tenant-name trove
        --os-auth-url http://<KeystoneIp>:5000/v2.0 image-list | awk '/trove-image/ {print $2}'`

---------
Run Trove
---------
* Run trove-api::

    # trove-api --config-file=<PathToTroveConf> &

* Run trove-taskmanager::

    # trove-taskmanager --config-file=<PathToTroveTaskmanagerConf> &

* Try executing a trove command, like get-instance. You must first issue an "auth login" to obtain an API key.::

    # trove-cli --username=trove --apikey=trove --tenant=trove --auth_url=http://<KeystoneIp>:35357/v2.0/tokens auth login

    # trove-cli instance list


Troubleshooting
===============

---------------------------------------------------------
No instance IPs in the output of 'trove-cli instance get'
---------------------------------------------------------

If Trove instance is created properly, is in the state ACTIVE, and is known for sure to be working,
but there are no IP addresses for the instance in the output of 'trove-cli instance get <id>', then make sure
the following lines are added to trove.conf::

    add_addresses = True
    network_label_regex = ^NETWORK_NAME$

where NETWORK_NAME should be replaced with real name of the nova network to which the instance is connected to.

One possible way to find the nova network name is to execute the 'nova list' command. The output will list
all OpenStack instances for the tenant, including network information. Look for ::

    NETWORK_NAME=IP_ADDRESS
