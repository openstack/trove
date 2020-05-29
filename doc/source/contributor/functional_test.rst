==========================
How to run functional test
==========================

Install DevStack
----------------
Functional test defined for Trove is supposed to be running against DevStack. It's recommended that the host on which the DevStack is running should support nested virtualization, otherwise errors or timeout may occur during the testing. Refer to https://docs.openstack.org/devstack/latest/guides/devstack-with-nested-kvm.html for how to check and enable nested virtualization on the host.

.. note::

    The functional test is different with Trove tempest test.

See `Install Trove in DevStack <https://docs.openstack.org/trove/latest/install/install-devstack.html>`_ for details.

Run tests
---------

For example, to run functional test with mysql datastore version 5.7.29, in trove source code directory, run:

.. code-block:: console

    ADMIN_PASSWORD=password \
    SERVICE_PASSWORD=password \
    tox -e trovestack gate-tests mysql mysql 5.7.29

* Parameters for ``gate-tests`` sub-command: ``<datastore_type> <test_group> <datastore_version>``. There are a few of test groups pre-defined: mysql, mysql-supported-single, mysql-supported-multi, mariadb-supported-single, mariadb-supported-multi, etc.
* ``ADMIN_PASSWORD`` and ``SERVICE_PASSWORD`` are the passwords defined in the ``local.conf`` file in devstack directory.
* By default, all the instances created during testing will be deleted automatically. For debugging purpose, if you want to keep the instances, you need to specify ``TESTS_DO_NOT_DELETE_INSTANCE=True``.