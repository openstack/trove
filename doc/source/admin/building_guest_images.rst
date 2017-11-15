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
and you wish to deliver MySQL version 5.5, then your guest instance is
a Nova instance running the Ubuntu operating system and will have
MySQL version 5.5 installed on it.

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

The Trove Guest Agent runs on the Trove Guest Instance.

------------------------------------------
Injected Configuration for the Guest Agent
------------------------------------------

When TaskManager launches the guest VM it injects the specific settings
for the guest into the VM, into the file /etc/trove/conf.d/guest_info.conf.
The file is injected one of three ways. If use_heat=True, it is injected
during the heat launch process. If use_nova_server_config_drive=True
it is injected via ConfigDrive. Otherwise it is passed to the nova
create call as the 'files' parameter and will be injected based on
the configuration of Nova; the Nova default is to discard the files.
If the settings in guest_info.conf are not present on the guest
Guest Agent will fail to start up.

------------------------------
Persistent Storage, Networking
------------------------------

The database stores data on persistent storage on Cinder (if
configured, see trove.conf and the volume_support parameter) or
ephemeral storage on the Nova instance. The database is accessible
over the network and the Guest Instance is configured for network
access by client applications.

Building Guest Images using DIB
===============================

A Trove Guest Image can be built with any tool that produces an image
accepted by Nova. In this document we describe how to build guest
images using the 'Disk Image Builder' (DIB) tool, and we focus on
building qemu images [1]_. DIB is an OpenStack tool and is available for
download at
https://git.openstack.org/cgit/openstack/diskimage-builder/tree/ or
https://pypi.python.org/pypi/diskimage-builder/0.1.38.

DIB uses a chroot'ed environment to construct the image. The goal is
to build a bare machine that has all the components required for
launch by Nova.

----------
Invocation
----------

You can download the DIB tool from OpenStack's public git
repository. Note that DIB works with Ubuntu and Fedora (RedHat). Other
operating systems are not yet fully supported.

.. code-block:: bash

   user@machine:/opt/stack$ git clone https://git.openstack.org/openstack/diskimage-builder
   Cloning into 'diskimage-builder'...
   remote: Counting objects: 8881, done.
   remote: Total 8881 (delta 0), reused 0 (delta 0)
   Receiving objects: 100% (8881/8881), 1.92 MiB | 0 bytes/s, done.
   Resolving deltas: 100% (4668/4668), done.
   Checking connectivity... done.
   user@machine:/opt/stack$ cd diskimage-builder
   user@machine:/opt/stack/diskimage-builder$ sudo pip install -r requirements.txt
   user@machine:/opt/stack/diskimage-builder$ sudo python setup.py install


Ensure that you have qemu-img [2]_ and kpartx installed.

The disk-image-create command is the main command in the DIB tool that
is used to build guest images for Trove. The disk-image-create command
takes the following options:

.. code-block:: bash

    user@machine:/opt/stack/diskimage-builder$ disk-image-create -h
    Usage: disk-image-create [OPTION]... [ELEMENT]...

    Options:
        -a i386|amd64|armhf -- set the architecture of the image(default amd64)
        -o imagename -- set the imagename of the output image file(default image)
        -t qcow2,tar -- set the image types of the output image files (default qcow2)
           File types should be comma separated
        -x -- turn on tracing
        -u -- uncompressed; do not compress the image - larger but faster
        -c -- clear environment before starting work
        --image-size size -- image size in GB for the created image
        --image-cache directory -- location for cached images(default ~/.cache/image-create)
        --max-online-resize size -- max number of filesystem blocks to support when resizing.
           Useful if you want a really large root partition when the image is deployed.
           Using a very large value may run into a known bug in resize2fs.
           Setting the value to 274877906944 will get you a 1PB root file system.
           Making this value unnecessarily large will consume extra disk space
           on the root partition with extra file system inodes.
        --min-tmpfs size -- minimum size in GB needed in tmpfs to build the image
        --no-tmpfs -- do not use tmpfs to speed image build
        --offline -- do not update cached resources
        --qemu-img-options -- option flags to be passed directly to qemu-img.
           Options need to be comma separated, and follow the key=value pattern.
        --root-label label -- label for the root filesystem.  Defaults to 'cloudimg-rootfs'.
        --ramdisk-element -- specify the main element to be used for building ramdisks.
           Defaults to 'ramdisk'.  Should be set to 'dracut-ramdisk' for platforms such
           as RHEL and CentOS that do not package busybox.
        --install-type -- specify the default installation type. Defaults to 'source'. Set
           to 'package' to use package based installations by default.
        -n skip the default inclusion of the 'base' element
        -p package[,package,package] -- list of packages to install in the image
        -h|--help -- display this help and exit

    ELEMENTS_PATH will allow you to specify multiple locations for the elements.

    NOTE: At least one distribution root element must be specified.

    Examples:
        disk-image-create -a amd64 -o ubuntu-amd64 vm ubuntu
        export ELEMENTS_PATH=~/source/tripleo-image-elements/elements
        disk-image-create -a amd64 -o fedora-amd64-heat-cfntools vm fedora heat-cfntools
    user@machine:/opt/stack/diskimage-builder$

The example command provided above would build a perfectly functional
Nova image with the 64 bit Fedora operating system.

In addition to the -a argument which specifies to build an amd64 (64
bit) image, and the -o which specifies the output file, the command
line lists the various elements that should be used in building the
image. The next section of this document talks about image elements.

Building a Trove guest image is a little more involved and the standard
elements (more about this later) are highly configurable through the use
of environment variables.

This command will create a guest image usable by Trove:

.. code-block:: bash

    # assign a suitable value for each of these environment
    # variables that change the way the elements behave.
    export HOST_USERNAME
    export HOST_SCP_USERNAME
    export GUEST_USERNAME
    export CONTROLLER_IP
    export TROVESTACK_SCRIPTS
    export SERVICE_TYPE
    export PATH_TROVE
    export ESCAPED_PATH_TROVE
    export SSH_DIR
    export GUEST_LOGDIR
    export ESCAPED_GUEST_LOGDIR
    export DIB_CLOUD_INIT_DATASOURCES="ConfigDrive"
    export DATASTORE_PKG_LOCATION
    export BRANCH_OVERRIDE

    # you typically do not have to change these variables
    export ELEMENTS_PATH=$TROVESTACK_SCRIPTS/files/elements
    export ELEMENTS_PATH+=:$PATH_DISKIMAGEBUILDER/elements
    export ELEMENTS_PATH+=:$PATH_TRIPLEO_ELEMENTS/elements
    export DIB_APT_CONF_DIR=/etc/apt/apt.conf.d
    export DIB_CLOUD_INIT_ETC_HOSTS=true
    local QEMU_IMG_OPTIONS="--qemu-img-options compat=1.1"

    # run disk-image-create that actually causes the image to be built
    $disk-image-create -a amd64 -o "${VM}" \
        -x ${QEMU_IMG_OPTIONS} ${DISTRO} ${EXTRA_ELEMENTS} vm \
        cloud-init-datasources ${DISTRO}-guest ${DISTRO}-${SERVICE_TYPE}

-----------------------------
Disk Image Builder 'Elements'
-----------------------------

DIB Elements are 'executed' by the disk-image-create command to
produce the guest image.  An element consists of a number of bash
scripts that are executed by DIB in a specific order to generate the
image. You provide the names of the elements that you would like
executed, in order, on the command line to disk-image-create.

Elements are executed within the chroot'ed environment while DIB is
run. Elements are executed in phases and the various phases are (in
order) root.d, extra-data.d, pre-install.d, install.d, post-install.d,
block-device.d, finalise.d [3]_, and cleanup.d [4]_. The latter
reference provides a very good outline on writing elements and is a
'must read'.

Some elements use environment.d to setup environment
variables. Element dependencies can be established using the
element-deps and element-provides files which are plain text files.

-----------------
Existing Elements
-----------------

DIB comes with some tools that are located in the elements directory.

.. code-block:: bash

    user@machine:/opt/stack/diskimage-builder/elements$ ls
    apt-conf                         dpkg                      ramdisk
    apt-preferences                  dracut-network            ramdisk-base
    apt-sources                      dracut-ramdisk            rax-nova-agent
    architecture-emulation-binaries  element-manifest          redhat-common
    baremetal                        enable-serial-console     rhel
    base                             epel                      rhel7
    cache-url                        fedora                    rhel-common
    centos7                          hwburnin                  rpm-distro
    cleanup-kernel-initrd            hwdiscovery               select-boot-kernel-initrd
    cloud-init-datasources           ilo                       selinux-permissive
    cloud-init-nocloud               ironic-agent              serial-console
    debian                           ironic-discoverd-ramdisk  source-repositories
    debian-systemd                   iso                       stable-interface-names
    debian-upstart                   local-config              svc-map
    deploy                           manifests                 uboot
    deploy-baremetal                 mellanox                  ubuntu
    deploy-ironic                    modprobe-blacklist        ubuntu-core
    deploy-kexec                     opensuse                  vm
    dhcp-all-interfaces              package-installs          yum
    dib-run-parts                    pip-cache                 zypper
    disable-selinux                  pkg-map
    dkms                             pypi

In addition, projects like TripleO [5]_ provide elements as well.

Trove provides a set of elements as part of the trove [6]_
project which will be described in the next section.

Trove Reference Elements
========================

Reference elements provided by Trove are part of the trove project.

In keeping with the philosophy of making elements 'layered', Trove
provides two sets of elements. The first implements the guest agent
for various operating systems and the second implements the database
for these operating systems.

---------------------------
Provided Reference Elements
---------------------------

The Trove reference elements are located in the
trove/integration/scripts/files/elements directory. The elements
[operating-system]-guest provide the Trove Guest capabilities and the
[operating-system]-[database] elements provide support for each
database on the specified database.

.. code-block:: bash

  user@machine:/opt/stack/trove/integration/scripts/files/elements$ ls -l
  total 56
  drwxrwxr-x 5 user group 4096 Jan  7 12:47 fedora-guest
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 fedora-mongodb
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 fedora-mysql
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 fedora-percona
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 fedora-postgresql
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 fedora-redis
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 ubuntu-cassandra
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 ubuntu-couchbase
  drwxrwxr-x 6 user group 4096 Jan  7 12:47 ubuntu-guest
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 ubuntu-mongodb
  drwxrwxr-x 4 user group 4096 Jan  7 12:47 ubuntu-mysql
  drwxrwxr-x 4 user group 4096 Jan  7 12:47 ubuntu-percona
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 ubuntu-postgresql
  drwxrwxr-x 3 user group 4096 Jan  7 12:47 ubuntu-redis
  user@machine:/opt/stack/trove/integration/scripts/files/elements$

With this infrastructure in place, and the elements from DIB and
TripleO accessible to the DIB command, one can generate the (for
example) Ubuntu guest image for Percona Server with the command line:

.. code-block:: bash

  ${DIB} -a amd64 -o ${output-file} Ubuntu vm \
      cloud-init-datasources ubuntu-guest ubuntu-percona

Where ${DIB} is the fully qualified path to the disk-image-create
command and ${output-file} is the name of the output file to be
created.

-------------------------------------------------------------------
Contributing Reference Elements When Implementing a New 'Datastore'
-------------------------------------------------------------------

When contributing a new datastore, you should contribute elements
that will allow any user of Trove to be able to build a guest image
for that datastore.

This is typically accomplished by submitting files into the
trove project, as above.

Getting the Guest Agent Code onto a Trove Guest Instance
========================================================

The guest agent code typically runs on the guest instance alongside
the database. There are two ways in which the guest agent code can be
placed on the guest instance and we describe both of these here.

----------------------------------------
Guest Agent Code Installed at Build Time
----------------------------------------

In this option, the guest agent code is built into the guest image,
thereby ensuring that all database instances that are launched with
the image will have the exact same version of the guest image.

This can be accomplished by placing suitable code in the elements for
the image and these elements will ensure that the guest agent code is
installed on the image.

--------------------------------------
Guest Agent Code Installed at Run Time
--------------------------------------

In this option, the guest agent code is not part of the guest image
and instead the guest agent code is obtained at runtime, potentially
from some well known location.

In devstack, this is implemented in trove-guest.upstart.conf and
trove-guest.systemd.conf. Shown below is the code from
trove-guest.upstart.conf (this code may change in the future and
is shown here as an example only). See the code highlighted below:

.. code-block:: bash

    description "Trove Guest"
    author "Auto-Gen"

    start on (filesystem and net-device-up IFACE!=lo)
    stop on runlevel [016]
    chdir /var/run
    pre-start script
        mkdir -p /var/run/trove
        chown GUEST_USERNAME:root /var/run/trove/

        mkdir -p /var/lock/trove
        chown GUEST_USERNAME:root /var/lock/trove/

        mkdir -p GUEST_LOGDIR
        chown GUEST_USERNAME:root GUEST_LOGDIR
        chmod +r /etc/guest_info

        # If /etc/trove does not exist, copy the trove source and the
        # guest agent config from the user's development environment
        if [ ! -d /etc/trove ]; then
    ->      sudo -u GUEST_USERNAME rsync -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' -avz --exclude='.*' HOST_SCP_USERNAME@NETWORK_GATEWAY:PATH_TROVE/ /home/GUEST_USERNAME/trove
            mkdir -p /etc/trove
    ->      sudo -u GUEST_USERNAME rsync -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' -avz --exclude='.*' HOST_SCP_USERNAME@NETWORK_GATEWAY:/etc/trove/trove-guestagent.conf ~GUEST_USERNAME/
            mv ~GUEST_USERNAME/trove-guestagent.conf /etc/trove/trove-guestagent.conf
        fi

    end script

    exec su -c "/home/GUEST_USERNAME/trove/contrib/trove-guestagent -config-file=/etc/guest_info --config-file=/etc/trove/trove-guestagent.conf" GUEST_USERNAME

In building an image for a production Trove deployment, it is a very
bad idea to use this mechanism. It makes sense in a development
environment where the thing that you are developing is in Trove and
part of the Guest Agent! This is because you get to merely boot a new
Trove instance and the freshly modified code gets run on the
Guest. But, in any other circumstance, it is much better to have the
guest image include the guest agent code.

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

Building Guest Images Using Standard Elements
=============================================

A very good reference for how one builds guest images can be found by
reviewing the trovestack script (trove/integration/scripts). Lower level
routines that actually invoke Disk Image Builder can be found in
trove/integration/scripts/functions_qemu.

The following block of code illustrates the most basic invocation of
DIB to create a guest image. This code is in
trove/integration/scripts/functions_qemu as part of the function
build_vm().  We look at this section of code in detail below.

.. code-block:: bash

    # assign a suitable value for each of these environment
    # variables that change the way the elements behave.
    export HOST_USERNAME
    export HOST_SCP_USERNAME
    export GUEST_USERNAME
    export CONTROLLER_IP
    export TROVESTACK_SCRIPTS
    export SERVICE_TYPE
    export PATH_TROVE
    export ESCAPED_PATH_TROVE
    export SSH_DIR
    export GUEST_LOGDIR
    export ESCAPED_GUEST_LOGDIR
    export DIB_CLOUD_INIT_DATASOURCES="ConfigDrive"
    export DATASTORE_PKG_LOCATION
    export BRANCH_OVERRIDE

    # you typically do not have to change these variables
    export ELEMENTS_PATH=$TROVESTACK_SCRIPTS/files/elements
    export ELEMENTS_PATH+=:$PATH_DISKIMAGEBUILDER/elements
    export ELEMENTS_PATH+=:$PATH_TRIPLEO_ELEMENTS/elements
    export DIB_APT_CONF_DIR=/etc/apt/apt.conf.d
    export DIB_CLOUD_INIT_ETC_HOSTS=true
    local QEMU_IMG_OPTIONS="--qemu-img-options compat=1.1"

    # run disk-image-create that actually causes the image to be built
    $disk-image-create -a amd64 -o "${VM}" \
        -x ${QEMU_IMG_OPTIONS} ${DISTRO} ${EXTRA_ELEMENTS} vm \
        cloud-init-datasources ${DISTRO}-guest ${DISTRO}-${SERVICE_TYPE}

Several of the environment variables referenced above are referenced
in the course of the Disk Image Building process.

For example, let's look at GUEST_LOGDIR. Looking at the element
elements/fedora-guest/extra-data.d/20-guest-systemd, we find:

.. code-block:: bash

        #!/bin/bash

        set -e
        set -o xtrace

        # CONTEXT: HOST prior to IMAGE BUILD as SCRIPT USER
        # PURPOSE: stages the bootstrap file and upstart conf file while replacing variables so that guest image is properly
        # configured

        source $_LIB/die

        [ -n "$TMP_HOOKS_PATH" ] || die "Temp hook path not set"

        [ -n "${GUEST_USERNAME}" ] || die "GUEST_USERNAME needs to be set to the user for the guest image"
        [ -n "${HOST_SCP_USERNAME}" ] || die "HOST_SCP_USERNAME needs to be set to the user for the host instance"
        [ -n "${CONTROLLER_IP}" ] || die "CONTROLLER_IP needs to be set to the ip address that guests will use to contact the controller"
        [ -n "${ESCAPED_PATH_TROVE}" ] || die "ESCAPED_PATH_TROVE needs to be set to the path to the trove directory on the trovestack host"
        [ -n "${TROVESTACK_SCRIPTS}" ] || die "TROVESTACK_SCRIPTS needs to be set to the trove/integration/scripts dir"
        [ -n "${ESCAPED_GUEST_LOGDIR}" ] || die "ESCAPED_GUEST_LOGDIR must be set to the escaped guest log dir"

        sed "s/GUEST_USERNAME/${GUEST_USERNAME}/g;s/GUEST_LOGDIR/${ESCAPED_GUEST_LOGDIR}/g;s/HOST_SCP_USERNAME/${HOST_SCP_USERNAME}/g;s/CONTROLLER_IP/${CONTROLLER_IP}/g;s/PATH_TROVE/${ESCAPED_PATH_TROVE}/g" \
        ${TROVESTACK_SCRIPTS}/files/trove-guest.systemd.conf >
        ${TMP_HOOKS_PATH}/trove-guest.service

As you can see, the value of GUEST_LOGDIR is used in the extra-data.d
script to appropriately configure the trove-guest.systemd.conf file.

This pattern is one that you can expect in your own building of guest
images.  The invocation of disk-image-create provides a list of
elements that are to be invoked 'in order'.

That list of elements is:

.. code-block:: bash

         ${DISTRO}
         ${EXTRA_ELEMENTS}
         vm
         cloud-init-datasources
         ${DISTRO}-guest
         ${DISTRO}-${SERVICE_TYPE}

When invoked to (for example) create a MySQL guest image on Ubuntu, we
can expect that DISTRO would be 'Ubuntu' and SERVICE_TYPE would be
MySQL. And therefore these would end up being the elements:

.. code-block:: bash

  ubuntu                        From diskimage-builder/elements/ubuntu
  vm                            From diskimage-builder/elements/vm
  cloud-init-datasources        From diskimage-builder/elements/cloud-init-datasources
  ubuntu-guest                  From trove/integration/scripts/files/elements/ubuntu-guest
  ubuntu-mysql                  From trove/integration/scripts/files/elements/ubuntu-mysql

References
==========

.. [1] For more information about QEMU, refer to http://wiki.qemu.org/Main_Page
.. [2] On Ubuntu, qemu-img is part of the package qemu-utils, on Fedora and RedHat it is part of the qemu package.
.. [3] User (especially in the USA) are cautioned about this spelling which once resulted in several sleepless nights.
.. [4] https://git.openstack.org/cgit/openstack/diskimage-builder/tree/README.rst#writing-an-element
.. [5] https://git.openstack.org/cgit/openstack/tripleo-image-elements/tree/elements
.. [6] https://git.openstack.org/cgit/openstack/trove/integration/tree/scripts/files/elements
