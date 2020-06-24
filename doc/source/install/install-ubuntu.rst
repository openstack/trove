.. _install-ubuntu:

Install and configure for Ubuntu
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the Database
service for Ubuntu 14.04 (LTS).

.. include:: common_prerequisites.txt


Install and configure components
--------------------------------

#. Install the packages:

   .. warning::

       Please be aware that the trove debian packages for Ubuntu are not
       usually up to date, especially when there are bugfixes for stable
       branch, the debian packages are not guaranteed to contain those changes.
       The recommended way to install OpenStack services is either using docker
       image with source code or installing source code inside a Python
       virutual environment.

   The commands to install Trove compoments:

   .. code-block:: console

      # apt-get update
      # apt-get install python-trove trove-common trove-api trove-taskmanager trove-conductor
      # pip3 install python-troveclient


.. include:: common_configure.txt


Finalize installation
---------------------

1. Restart the Database services:

   .. code-block:: console

      # service trove-api restart
      # service trove-taskmanager restart
      # service trove-conductor restart
