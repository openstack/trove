==========================
How to run functional test
==========================

For historical reasons, prior to Victoria, Trove was not using Tempest for running functional test. All the functional tests are organized using the Python library `Proboscis <https://pythonhosted.org/proboscis/>`_， which has not been maintained for a long time.

However, Trove team is not going to migrate all the existing functional tests to `trove-tempest-plugin <https://github.com/openstack/trove-tempest-plugin>`_ due to lack of upstream maintainers, new functional tests should go with trove-tempest-plugin, new features shouldn't break the existing functional tests.

.. note::

   In this guide, "functional test" refers to the existing functional test cases in trove repo, "tempest test" refers to test cases in trove-tempest-plugin repo.

Since Victoria, the upstream CI jobs keep failing because of the poor performance of the CI devstack host (virtual machine), trove project contributors should guarantee any proposed patch passes both the functional test and trove tempest test by themselves, the code reviewer may ask for the test result.

Install DevStack
----------------

It's recommended that the DevStack host should support nested virtualization, otherwise errors or timeouts may occur during the testing. Refer to https://docs.openstack.org/devstack/latest/guides/devstack-with-nested-kvm.html for how to check and enable nested virtualization on the host.

See `Install Trove in DevStack <https://docs.openstack.org/trove/latest/install/install-devstack.html>`_ for development environment installation.

Run functional test
-------------------

Trove uses ``trovestack`` to run functional test. ``trovestack`` is responsible for:

* Install necessary packages
* Build and register guest image (if the image doesn't exist in Glance)
* Register datastore and version
* Prepare the test config file ``/etc/trove/test.conf``.
* Create Nova flavors used for testing.
* Trigger the actual functional tests.

For example, to run functional test with MySQL datastore version 5.7.29, in trove source code directory, run:

.. code-block:: console

   ADMIN_PASSWORD=password SERVICE_PASSWORD=password \
   tox -e trovestack gate-tests \
   mysql \
   mysql \
   5.7.29

* Parameters for ``gate-tests`` sub-command: ``<datastore_type> <test_group> <datastore_version>``. There are a few of test groups pre-defined: mysql, mysql-supported-single, mysql-supported-multi, mariadb-supported-single, mariadb-supported-multi, etc.
* ``ADMIN_PASSWORD`` and ``SERVICE_PASSWORD`` are the passwords defined in the ``local.conf`` file in devstack directory.
* By default, all the instances created during testing will be deleted automatically. For debugging purposes, if you want to keep the instances, specify ``TESTS_DO_NOT_DELETE_INSTANCE=True``.

Another example of running tests for MariaDB 10.4.13:

.. code-block:: console

   ADMIN_PASSWORD=password SERVICE_PASSWORD=password \
   tox -e trovestack gate-tests \
   mariadb \
   mariadb-supported-single \
   10.4.13

Run tempest test
----------------

Trove tempest test can be running in the same way as other openstack tempest test. See `Tempest user guide <https://docs.openstack.org/tempest/latest/overview.html#quickstart>`_.

Prepare tempest config for trove-tempest-plugin before running, an example config:

.. code-block:: ini

   [auth]
   tempest_roles = ResellerAdmin

   [network]
   public_network_id = 48e5e576-ec48-4597-bfee-658e358f31a9

   [database]
   enabled_datastores=mysql
   default_datastore_versions = mysql:5.7.30
   pre_upgrade_datastore_versions = mysql:5.7.29
   flavor_id = 28153197-6690-4485-9dbc-fc24489b0683
   resize_flavor_id = d2
   volume_type = lvmdriver-1
   database_build_timeout = 1800
   shared_network =

Some example commands:

#. List all the MySQL related test cases:

   .. code-block:: console

      tempest run --list-tests --regex ^trove_tempest_plugin | grep -i mysql | sort

#. Run one single test:

   .. code-block:: console

      tempest run --concurrency 1 --regex ^trove_tempest_plugin.tests.scenario.test_replication.TestReplicationMySQL.test_replication
