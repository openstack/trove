..
      Copyright (c) 2020 Catalyst Cloud

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

===========================
Running Trove in production
===========================

This document is not a definitive guide for deploying Trove in every production
environment. There are many ways to deploy Trove depending on the specifics and
limitations of your situation. We hope this document provides the cloud
operator or distribution creator with a basic understanding of how the Trove
components fit together practically. Through this, it should become more
obvious how components of Trove can be divided or duplicated across physical
hardware in a production cloud environment to aid in achieving scalability and
resiliency for the database as a service software.

In the interest of keeping this guide somewhat high-level and avoiding
obsolescence or operator/distribution-specific environment assumptions by
specifying exact commands that should be run to accomplish the tasks below, we
will instead just describe what needs to be done and leave it to the cloud
operator or distribution creator to "do the right thing" to accomplish the task
for their environment. If you need guidance on specific commands to run to
accomplish the tasks described below, we recommend reading through the
``plugin.sh`` script in devstack subdirectory of this project. The devstack
plugin exercises all the essential components of Trove in the right order, and
this guide will mostly be an elaboration of this process.


Environment Assumptions
-----------------------
The scope of this guide is to provide a basic overview of setting up all
the components of Trove in a production environment, assuming that the
default in-tree drivers and components are going to be used.

For the purposes of this guide, we will therefore assume the following core
components have already been set up for your production OpenStack environment:

* RabbitMQ
* MySQL
* Keystone
* Nova
* Cinder
* Neutron
* Glance
* Swift


Production Deployment Walkthrough
---------------------------------


Create Trove Service User
~~~~~~~~~~~~~~~~~~~~~~~~~
By default Trove will use the 'trove' user with 'admin' role in 'service'
tenant for both keystone authentication and interactions with all other
services.


Service Tenant Deployment
~~~~~~~~~~~~~~~~~~~~~~~~~
In production, almost all the cloud resources(except the Swift objects for
backup data) created for a Trove instance should be only visible to the Trove
service user. As DBaaS users, they should only see a Trove instance after
creating, and know nothing about the Nova VM, Cinder volume, Neutron management
network and security groups under the hood. The only way to operate Trove
instance is to interact with `Trove API
<https://docs.openstack.org/api-ref/database/>`_.

Service tenant deployment is the default configuration in Trove since Ussuri
release.


Install Trove Controller Software
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Trove controller services should be put somewhere that has access to the
database, the oslo messaging system, and other OpenStack services. Trove uses
the standard python setuptools, so installation of the software itself should
be straightforward.

Running multiple instances of the individual Trove controller components on
separate physical hosts is recommended in order to provide scalability and
availability of the controller software.


Management Network
~~~~~~~~~~~~~~~~~~
Trove makes use of a "Management Network" exclusively that the controller uses
to talk to guest agent running inside Trove instance and vice versa. All the
instances that Trove deploys will have interfaces on this network. Therefore,
it's important that the subnet deployed on this network be sufficiently large
to allow for the maximum number of instances and controllers likely to be
deployed throughout the lifespan of the cloud installation.

Usually, after a Trove instance is created, there are 2 nics attached to the
instance VM, one for the database traffic on user-defined network, one for
management purpose. Trove will check if the user's subnet conflicts with the
management network.

You can also create a management Neutron security group that will be applied to
the management port. Basically, nothing needs to be allowed to access the
management port, most of the network communication within the Trove instance is
egress traffic(e.g. the guest agent initiates connection with RabbitMQ).
However, It can be helpful to allow SSH access to the Trove instance from the
controller for troubleshooting purposes (ie. TCP port 22), though this is not
strictly necessary in production environments.

In order to SSH into the Trove instance(as mentioned above, it's helpful but
not necessary), the cloud administrators need to create and config a Nova
keypair.

Finally, you need to add routing or interfaces to this network so that the
Trove guest agent running inside the instance is able to connect with RabbitMQ.


RabbitMQ Considerations
~~~~~~~~~~~~~~~~~~~~~~~
Both trove-taskmanager and trove-conductor talk to guest agent inside Trove
instance via the messaging system, ie. RabbitMQ. Once the guest agent is up and
running, it's listening on a message queue named ``guestagent.<guest ID>``
specifically set up for that particular instance, receiving requests from
trove-taskmanager for operations like set up the database software, create
databases and users, restart database service etc. At the mean while,
trove-guestagent periodically sends status update information to
trove-conductor through the messaging system.

With all that said, a proper RabbitMQ user name and password need to be
configured in the trove-guestagent config file, which may bring security
concern for the cloud deployers. If the guest instance is compromised, then
guest credentials are compromised, which means the messaging system is
compromised.

As part of the solution, Trove introduced a `security enhancement
<https://docs.openstack.org/trove/latest/admin/secure_oslo_messaging.html>`_ in
Ocata release, using encryption keys to protect the messages between the
control plane and the guest instances, which guarantees that one compromised
guest instance doesn't affect other instances nor other cloud users.


Configuring Trove
~~~~~~~~~~~~~~~~~
The default Trove configuration file location is ``/etc/trove/trove.conf``. You
can generate a sample config file by running:

.. code-block:: console

    cd <trove dir>
    pip install -e .
    oslo-config-generator --namespace trove.config --namespace oslo.messaging --namespace oslo.log --namespace oslo.policy --output-file /etc/trove/trove.conf.sample

The typical config options (not a full list) are:

DEFAULT group
  enable_secure_rpc_messaging
    Should RPC messaging traffic be secured by encryption.

  taskmanager_rpc_encr_key
    The key (OpenSSL aes_cbc) used to encrypt RPC messages sent to
    trove-taskmanager, used by trove-api.

  instance_rpc_encr_key
    The key (OpenSSL aes_cbc) used to encrypt RPC messages sent to guest
    instance from trove-taskmanager and the messages sent from guest instance
    to trove-conductor. This key is generated by trove-taskmanager
    automatically and is injected into the guest instance when creating.

  inst_rpc_key_encr_key
    The database encryption key to encrypt per-instance PRC encryption key
    before storing to Trove database.

  management_networks
    The management network, currently only one management network is allowed.

  management_security_groups
    List of the management security groups that are applied to the management
    port of the database instance.

  cinder_volume_type
    Cinder volume type used to create volume that is attached to Trove
    instance.

  nova_keypair
    Name of a Nova keypair to inject into a database instance to enable SSH
    access.

  default_datastore
    The default datastore id or name to use if one is not provided by the user.
    If the default value is None, the field becomes required in the instance
    create request.

  max_accepted_volume_size
    The default maximum volume size (in GB) for an instance.

  max_instances_per_tenant
    Default maximum number of instances per tenant.

  max_backups_per_tenant
    Default maximum number of backups per tenant.

  transport_url
    The messaging server connection URL, e.g.
    ``rabbit://stackrabbit:password@10.0.119.251:5672/``

  control_exchange
    The Trove exchange name for the messaging service, could be overridden by
    an exchange name specified in the transport_url option.

  reboot_time_out
    Maximum time (in seconds) to wait for a server reboot.

  usage_timeout
    Maximum time (in seconds) to wait for Trove instance to become ACTIVE for
    creation.

  restore_usage_timeout
    Maximum time (in seconds) to wait for Trove instance to become ACTIVE for
    restore.

  agent_call_high_timeout
    Maximum time (in seconds) to wait for Guest Agent 'slow' requests (such as
    restarting the instance server) to complete.

keystone_authtoken group
  Like most of other OpenStack services, Trove uses `Keystone Authentication
  Middleware
  <https://docs.openstack.org/keystonemiddleware/latest/middlewarearchitecture.html>`_
  for authentication and authorization.

service_credentials group
  Options in this section are pretty much like the options in
  ``keystone_authtoken``, but you can config another service user for Trove to
  communicate with other OpenStack services like Nova, Neutron, Cinder, etc.

  * auth_url
  * region_name
  * project_name
  * username
  * password
  * project_domain_name
  * user_domain_name

database group
  connection
    The SQLAlchemy connection string to use to connect to the database, e.g.
    ``mysql+pymysql://root:password@127.0.0.1/trove?charset=utf8``

The cloud administrator also needs to provide a policy file
``/etc/trove/policy.json`` if the default API access policies don't satisfy the
requirement. To generate a sample policy file with all the default policies,
run ``tox -egenpolicy`` in the repo folder and the new file will be located in
``etc/trove/policy.yaml.sample``.


Initialize Trove Database
~~~~~~~~~~~~~~~~~~~~~~~~~
This is controlled through `sqlalchemy-migrate
<https://code.google.com/archive/p/sqlalchemy-migrate/>`_ scripts under the
trove/db/sqlalchemy/migrate_repo/versions directory in this repository. The
script ``trove-manage`` (which should be installed together with Trove
controller software) could be used to aid in the initialization of the Trove
database. Note that this tool looks at the ``/etc/trove/trove.conf`` file for
its database credentials, so initializing the database must happen after Trove
is configured.


Launching the Trove Controller
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
We recommend using upstart / systemd scripts to ensure the components of the
Trove controller are all started and kept running.


Preparing the Guest Images
~~~~~~~~~~~~~~~~~~~~~~~~~~
Now that the Trove system is installed, the next step is to build the images
that we will use for the DBaaS to function properly. This is possibly the most
important step as this will be the gold standard that Trove will use for a
particular data store.

.. note::

    For the sake of simplicity and especially for testing, we can use the
    prebuilt images that are available from OpenStack itself. These images
    should strictly be used for testing and development use and should not be
    used in a production environment. The images are available for download and
    are located at http://tarballs.openstack.org/trove/images/.

From Victoria release, Trove uses a single guest image for all the supported
datastores. Database service is running as docker container inside the trove
instance which simplifies the datastore management and maintenance.

For use with production systems, it is recommended to create and maintain your
own images in order to conform to standards set by the company's security team.
In Trove community, we use `Disk Image Builder(DIB)
<https://docs.openstack.org/diskimage-builder/latest/>`_ to create Trove
images, all the elements are located in ``integration/scripts/files/elements``
folder in the repo.

Trove provides a script named ``trovestack`` to help build the image, refer to
`Build images using trovestack
<https://docs.openstack.org/trove/latest/admin/building_guest_images.html#build-images-using-trovestack>`_
for more information. Make sure to use ``dev_mode=false`` for production
environment.

After image is created successfully, the cloud administrator needs to upload
the image to Glance and make it only accessible to service users. It's
recommended to use tags when creating Glance image.


Preparing the Datastore
~~~~~~~~~~~~~~~~~~~~~~~
After image is uploaded, the cloud administrator should create datastores,
datastore versions and the configuration parameters for the particular version.

It's recommended to config a default version for each datastore.

``trove-manage`` can be only used on trove controller node.

Command examples:

.. code-block:: console

    $ # Creating datastore 'mysql' and datastore version 5.7.29.
    $ openstack datastore version create 5.7.29 mysql mysql "" \
      --image-tags trove,mysql \
      --active --default
    $ # Register configuration parameters for the datastore version
    $ trove-manage db_load_datastore_config_parameters mysql 5.7.29 ${trove_repo_dir}}/trove/templates/mysql/validation-rules.json


Quota Management
~~~~~~~~~~~~~~~~
The amount of resources that could be created by each OpenStack project is
controlled by quota. The default resource quota for each project is set in
Trove config file as follows unless changed by the cloud administrator via
`Quota API
<https://docs.openstack.org/api-ref/database/#update-resources-quota-for-a-specific-project>`_.

.. code-block:: ini

    [DEFAULT]
    max_instances_per_tenant = 10
    max_backups_per_tenant = 50


Trove Deployment Verfication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If all of the above instructions have been followed, it should now be possible
to deploy Trove instances using the OpenStack CLI, communicating with the Trove
V1 API.

Refer to `Create and access a database
<https://docs.openstack.org/trove/latest/user/create-db.html>`_ for detailed
steps.
