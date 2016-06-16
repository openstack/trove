.. _install-ubuntu:

Install and configure for Ubuntu
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the Orchestration
service for Ubuntu 14.04 (LTS).

This section assumes that you already have a working OpenStack
environment with at least the following components installed:
Compute, Image Service, Identity.

* If you want to do backup and restore, you also need Object Storage.

* If you want to provision datastores on block-storage volumes, you also
  need Block Storage.


.. include:: common_prerequisites.txt


Install and configure components
--------------------------------

#. Install the packages:

   .. code-block:: console

      # apt-get update

      # apt-get install python-trove python-troveclient \
        python-glanceclient trove-common trove-api trove-taskmanager \
        trove-conductor


.. include:: common_configure.txt


Finalize installation
---------------------

1. Due to a bug in the Ubuntu packages, edit the service definition files
   to use the correct configuration settings.

   To do this, navigate to ``/etc/init`` and edit the following files
   as described below:

   ``trove-taskmanager.conf``

   ``trove-conductor.conf``

   (Note that, although they have the same names, these files are
   in a different location and have different content than the similarly
   named files you edited earlier in this procedure.)

   In each file, find this line:

   .. code-block:: ini

      exec start-stop-daemon --start --chdir /var/lib/trove \
         --chuid trove:trove --make-pidfile \
         --pidfile /var/run/trove/trove-conductor.pid \
         --exec /usr/bin/trove-conductor -- \
         --config-file=/etc/trove/trove.conf ${DAEMON_ARGS}

   Note that ``--config-file`` incorrectly points to ``trove.conf``.

   In ``trove-taskmanager.conf``, edit ``config-file`` to point to
   ``/etc/trove/trove-taskmanager.conf``.

   In ``trove-conductor.conf``, edit ``config-file`` to point to
   ``/etc/trove/trove-conductor.conf``.

2. Restart the Database services:

   .. code-block:: console

      # service trove-api restart
      # service trove-taskmanager restart
      # service trove-conductor restart
