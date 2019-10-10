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

High Level Overview of a Trove Guest Instance
=============================================

At the most basic level, a Trove Guest Instance is a Nova instance
launched by Trove in response to a create command. For most of this
document, we will confine ourselves to single instance databases; in
other words, without the additional complexity of replication or
mirroring. Guest instances and Guest images for replicated and
mirrored database instances will be addressed specifically in later
sections of this document.

This section describes the various components of a Trove Guest
Instance.

-----------------------------
Operating System and Database
-----------------------------

A Trove Guest Instance contains at least a functioning Operating
System and the database software that the instance wishes to provide
(as a Service). For example, if your chosen operating system is Ubuntu
and you wish to deliver MySQL version 5.7, then your guest instance is
a Nova instance running the Ubuntu operating system and will have
MySQL version 5.7 installed on it.

-----------------
Trove Guest Agent
-----------------

Trove supports multiple databases, some of them are relational (RDBMS)
and some are non-relational (NoSQL). In order to provide a common
management interface to all of these, the Trove Guest Instance has on
it a 'Guest Agent'. The Trove Guest Agent is a component of the
Trove system that is specific to the database running on that Guest
Instance.

The purpose of the Trove Guest Agent is to implement the Trove Guest
Agent API for the specific database. This includes such things as the
implementation of the database 'start' and 'stop' commands. The Trove
Guest Agent API is the common API used by Trove to communicate with
any guest database, and the Guest Agent is the implementation of that
API for the specific database.

The Trove Guest Agent runs inside the Trove Guest Instance.

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

-----------------------------
Build images using trovestack
-----------------------------

``trovestack`` is the recommended tooling provided by Trove community to build
the guest images. Before running ``trovestack`` command, go to the scripts
folder:

.. code-block:: console

    git clone https://opendev.org/openstack/trove
    cd trove/integration/scripts

The trove guest agent image could be created by running the following command:

.. code-block:: console

    $ ./trovestack build-image \
        ${datastore_type} \
        ${guest_os} \
        ${guest_os_release} \
        ${dev_mode} \
        ${guest_username} \
        ${imagepath}

* Currently, only ``guest_os=ubuntu`` and ``guest_os_release=xenial`` are fully
  tested and supported.

* Default input values:

  .. code-block:: ini

      datastore_type=mysql
      guest_os=ubuntu
      guest_os_release=xenial
      dev_mode=true
      guest_username=ubuntu
      imagepath=$HOME/images/trove-${guest_os}-${guest_os_release}-${datastore_type}

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
  * ``GUEST_WORKING_DIR``: The place to save the guest image, default value is
    ``$HOME/images``.
  * ``TROVE_BRANCH``: Only used in dev mode. The branch name of Trove code
    repository, by default it's master, use other branches as needed such as
    stable/train.

For example, in order to build a MySQL image for Ubuntu Xenial operating
system in development mode:

.. code-block:: console

    $ ./trovestack build-image mysql ubuntu xenial true

Once the image build is finished, the cloud administrator needs to register the
image in Glance and register a new datastore or version in Trove using
``trove-manage`` command, e.g. after building an image for MySQL 5.7.1:

.. code-block:: console

    $ openstack image create ubuntu-mysql-5.7.1-dev \
      --public \
      --disk-format qcow2 \
      --container-format bare \
      --file ~/images/ubuntu-xenial-mysql.qcow2
    $ trove-manage datastore_version_update mysql 5.7.1 mysql $image_id "" 1

If you see anything error or need help for the image creation, please ask help
either in ``#openstack-trove`` IRC channel or sending emails to
openstack-discuss@lists.openstack.org mailing list.
