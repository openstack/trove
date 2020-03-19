.. _install-ubuntu:

Install and configure for Ubuntu
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the Database
service for Ubuntu 14.04 (LTS).

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

1. Restart the Database services:

   .. code-block:: console

      # service trove-api restart
      # service trove-taskmanager restart
      # service trove-conductor restart
