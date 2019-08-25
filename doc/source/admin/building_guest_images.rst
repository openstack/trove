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

When Trove receives a command to create a guest instance, it does so
by launching a Nova instance based on the appropriate guest image that
is stored in Glance.

To operate Trove it is vital to have a properly constructed guest
image, and while tools are provided that help you build them,
the Trove project itself does not distribute guest images. This
document shows you how to build guest images for use with Trove.

It is assumed that you have a working OpenStack deployment with the
key services like Keystone, Glance, Swift, Cinder, Nova and networking
through either Nova Networks or Neutron where you will deploy the
guest images. It is also assumed that you have Trove functioning and
all the Trove services operating normally. If you don't have these
prerequisites, this document won't help you get them. Consult the
appropriate documentation for installing and configuring OpenStack for
that.

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

When TaskManager launches the guest VM it injects the specific settings
for the guest into the VM, into the file /etc/trove/conf.d/guest_info.conf.
The file is injected one of three ways.

If ``use_nova_server_config_drive=True``, it is injected via ConfigDrive.
Otherwise it is passed to the nova create call as the 'files' parameter and
will be injected based on the configuration of Nova; the Nova default is to
discard the files. If the settings in guest_info.conf are not present on the
guest Guest Agent will fail to start up.

------------------------------
Persistent Storage, Networking
------------------------------

The database stores data on persistent storage on Cinder (if
configured, see trove.conf and the volume_support parameter) or
ephemeral storage on the Nova instance. The database service is accessible
over the tenant network provided when creating the database instance.

The cloud administrator is able to config a management
networks(``CONF.management_networks``) that is invisible to the cloud tenants,
database instance can talk to the control plane services(e.g. the message
queue) via that network.

Building Guest Images using DIB
===============================

A Trove Guest Image can be built with any tool that produces an image
accepted by Nova. In this document we describe how to build guest
images using the
`'Disk Image Builder' (DIB) <https://docs.openstack.org/diskimage-builder/latest/>`_
tool, and we focus on building qemu images.

DIB uses a chroot'ed environment to construct the image. The goal is
to build a bare machine that has all the components required for
launch by Nova.

----------------------------
Build image using trovestack
----------------------------

Trove provides a script called ``trovestack`` that could do most of the
management and test tasks. Refer to the "Build guest agent image" section
in
`trovestack document <https://github.com/openstack/trove/blob/master/integration/README.md>`_
for how to build trove guest agent images.

-----------------------------
Disk Image Builder 'Elements'
-----------------------------

DIB Elements are 'executed' by the disk-image-create command to
produce the guest image.  An element consists of a number of bash
scripts that are executed by DIB in a specific order to generate the
image. You provide the names of the elements that you would like
executed, in order, on the command line to disk-image-create.

DIB comes with some
`built-in elements <https://docs.openstack.org/diskimage-builder/latest/elements.html>`_.
In addition, projects like
`TripleO <https://github.com/openstack/tripleo-image-elements>`_ provide
elements as well.

Trove also provides a set of its own elements. In keeping with the philosophy
of making elements 'layered', Trove provides two sets of elements. The first
implements the guest agent for various operating systems and the second
implements the database for these operating systems.

-------------------------------------------------------------------
Contributing Reference Elements When Implementing a New 'Datastore'
-------------------------------------------------------------------

When contributing a new datastore, you should contribute elements
that will allow any user of Trove to be able to build a guest image
for that datastore.

Considerations in Building a Guest Image
========================================

In building a guest image, there are several considerations that one
must take into account. Some of the ones that we have encountered are
described below.

---------------------------------------
Speed of Launch and Start-up Activities
---------------------------------------

The actions performed on first boot can be very expensive and may
impact the time taken to launch a new guest instance. So, for example,
guest images that don't have the database software pre-installed and
instead download and install during launch could take longer to
launch.

In building a guest image, therefore care should be taken to ensure
that activities performed on first boot are traded off against the
demands for start-time.

---------------------------------------------------------
Database licensing, and Database Software Download Issues
---------------------------------------------------------

Some database software downloads are licensed and manual steps are
required in order to obtain the installable software. In other
instances, no repositories may be setup to serve images of a
particular database.  In these cases, it is suggested that an extra
step be used to build the guest image.

User Manually Downloads Database Software
-----------------------------------------

The user manually downloads the database software in a suitable format
and places it in a specified location on the machine that will be used
to build the guest image.

An environment variable 'DATASTORE_PKG_LOCATION' is set to point
to this location. It can be a single file (for example new_db.deb)
or a folder (for example new_db_files) depending on what the elements
expect. In the latter case, the folder would need to contain all the
files that the elements need in order to install the database software
(a folder would typically be used only if more than one file was
required).

Use an extra-data.d Folder
--------------------------

Use an extra-data.d folder for the element and copy the file
into the image

Steps in extra-data.d are run first, and outside the DIB chroot'ed
environment. The step here can copy the installable from
DATASTORE_PKG_LOCATION into the image
(typically into TMP_HOOKS_PATH).

For example, if DATASTORE_PKG_LOCATION contains the full path to an
installation package, an element in this folder could contain the
following line:

.. code-block:: bash

  dd if=${DATASTORE_PKG_LOCATION} of=${TMP_HOOKS_PATH}/new_db.deb

Use an install.d Step to Install the Software
---------------------------------------------

A standard install.d step can now install the software from
TMP_HOOKS_DIR.

For example, an element in this folder could contain:

.. code-block:: bash

  dpkg -i ${TMP_HOOKS_PATH}/new_db.deb

Once elements have been set up that expect a package to be available,
the guest image can be created by executing the following:

.. code-block:: bash

  DATASTORE_PKG_LOCATION=/path/to/new_db.deb ./script_to_call_dib.sh

Assuming the elements for new_db are available in the trove
repository, this would equate to:

.. code-block:: bash

  DATASTORE_PKG_LOCATION=/path/to/new_db.deb ./trovestack kick-start new_db
