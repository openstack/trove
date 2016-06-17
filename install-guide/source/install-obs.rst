.. _install-obs:


Install and configure for openSUSE and SUSE Linux Enterprise
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section describes how to install and configure the Database service
for openSUSE Leap 42.1 and SUSE Linux Enterprise Server 12 SP1.

.. include:: common_prerequisites.txt

Install and configure components
--------------------------------

#. Install the packages:

   .. code-block:: console

      # zypper --quiet --non-interactive install python-oslo.db \
        python-MySQL-python

      # zypper --quiet --non-interactive install openstack-trove-api \
        openstack-trove-taskmanager openstack-trove-conductor \
        openstack-trove-guestagent


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

