.. _build_guest_images:

.. role:: bash(code)
   :language: bash

=========================================
Building Guest Images for OpenStack Trove
=========================================

.. If section numbers are desired, unindent this
    .. sectnum::

.. If a TOC is desired, unindent this
    .. contents::

Overview
========

When Trove receives a command to create a database instance, it does so by
launching a Nova instance based on the appropriate guest image that is
stored in Glance. This document shows you the steps to build the guest images.

.. note::

    For testing purpose, the Trove guest images of some specific databases are
    periodically built and published in
    http://tarballs.openstack.org/trove/images/ in Trove upstream CI.

    Additionally, if you install Trove in devstack environment, the guest image
    is created and registered in Glance automatically, unless it's disabled by
    setting ``TROVE_ENABLE_IMAGE_BUILD=false`` in devstack local.conf file.

High Level Overview of a Trove Guest Instance
=============================================

At the most basic level, a Trove Guest Instance is a Nova instance launched by
Trove in response to a create command. This section describes the various
components of a Trove Guest Instance.

----------------
Operating System
----------------

The officially supported operating system is Ubuntu, based on which the
functional tests are running.

------
Docker
------

Since Vitoria release, all the datastore services are installed by docker
container inside the Trove instance, so docker should be installed when
building the guest image.

-----------------
Trove Guest Agent
-----------------

The guest agent runs inside the Nova instances that are used to run the
database engines. The agent listens to the messaging bus for the topic and is
responsible for actually translating and executing the commands that are sent
to it by the task manager component for the particular datastore.

Trove guest agent is responsible for datastore docker container management.

------------------------------------------
Injected Configuration for the Guest Agent
------------------------------------------

When TaskManager launches the guest VM it injects config files into the
VM, including:

* ``/etc/trove/conf.d/guest_info.conf``: Contains some information about
  the guest, e.g. the guest identifier, the tenant ID, etc.
* ``/etc/trove/conf.d/trove-guestagent.conf``: The config file for the
  guest agent service.

------------------------------
Persistent Storage, Networking
------------------------------

The database stores data on persistent storage on Cinder (if
``CONF.volume_support=True``) or ephemeral storage on the Nova instance. The
database service is accessible over the tenant network provided when creating
the database instance.

The cloud administrator is able to config management
networks(``CONF.management_networks``) that is invisible to the cloud tenants,
but used for communication between database instance and the control plane
services(e.g. the message queue).

Building Guest Images
=====================

Since Victoria release, a single trove guest image can be used for different
datastores, it's unnecessary to maintain different images for differnt
datastores.

-----------------------------
Build images using trovestack
-----------------------------

``trovestack`` is the recommended tooling provided by Trove community to build
the guest images. Before running ``trovestack`` command:

.. code-block:: console

    git clone https://opendev.org/openstack/trove
    cd trove/integration/scripts

The trove guest image could be created by running the following command:

.. code-block:: console

    $ ./trovestack build-image \
        ${guest_os} \
        ${guest_os_release} \
        ${dev_mode} \
        ${guest_username} \
        ${output_image_path}

* Currently, only ``guest_os=ubuntu`` and ``guest_os_release=bionic`` are fully
  tested and supported.

* Default input values:

  .. code-block:: ini

      guest_os=ubuntu
      guest_os_release=bionic
      dev_mode=true
      guest_username=ubuntu
      output_image_path=$HOME/images/trove-guest--${guest_os}-${guest_os_release}-dev

* ``dev_mode=true`` is mainly for testing purpose for trove developers and it's
  necessary to build the image on the trove controller host, because the host
  and the guest VM need to ssh into each other without password. In this mode,
  when the trove guest agent code is changed, the image doesn't need to be
  rebuilt which is convenient for debugging. Trove guest agent will ssh into
  the controller node and download trove code during the service initialization.

* if ``dev_mode=false``, the trove code for guest agent is injected into the
  image at the building time. Now ``dev_mode=false`` is still in experimental
  and not considered production ready yet.

* Some other global variables:

  * ``HOST_SCP_USERNAME``: Only used in dev mode, this is the user name used by
    guest agent to connect to the controller host, e.g. in devstack
    environment, it should be the ``stack`` user.

For example, in order to build a guest image for Ubuntu Bionic operating
system in development mode:

.. code-block:: console

    $ ./trovestack build-image ubuntu bionic true ubuntu

Once the image build is finished, the cloud administrator needs to register the
image in Glance and register a new datastore or version in Trove using
``trove-manage`` command, e.g. after building an image for MySQL 5.7.29:

.. code-block:: console

    $ openstack image create trove-guest-ubuntu-bionic \
      --private \
      --disk-format qcow2 \
      --container-format bare \
      --file ~/images/trove-guest-ubuntu-bionic-dev.qcow2
    $ trove-manage datastore_version_update mysql 5.7.29 mysql $image_id "" 1
    $ trove-manage db_load_datastore_config_parameters mysql 5.7.29 ${trove_repo_dir}/trove/templates/mysql/validation-rules.json

If you see anything error or need help for the image creation, please ask help
either in ``#openstack-trove`` IRC channel or sending emails to
openstack-discuss@lists.openstack.org mailing list.
