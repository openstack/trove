.. _install-rdo:

Install and configure for Red Hat Enterprise Linux and CentOS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. warning::

    This guide is not tested since stable/train.

This section describes how to install and configure the Database service
for Red Hat Enterprise Linux 7 and CentOS 7.

.. include:: common_prerequisites.txt

Install and configure components
--------------------------------

#. Install the packages:

   .. code-block:: console

      # yum install openstack-trove python-troveclient

.. include:: common_configure.txt

Finalize installation
---------------------

Start the Database services and configure them to start when
the system boots:

.. code-block:: console

   # systemctl enable openstack-trove-api.service \
     openstack-trove-taskmanager.service \
     openstack-trove-conductor.service

   # systemctl start openstack-trove-api.service \
     openstack-trove-taskmanager.service \
     openstack-trove-conductor.service
