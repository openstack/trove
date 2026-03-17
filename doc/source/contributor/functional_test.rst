==========================
How to run functional test
==========================

History
-------

For historical reasons, prior to Victoria, Trove was not using Tempest for running functional test. All the functional tests are organized using the Python library `Proboscis <https://pythonhosted.org/proboscis/>`_， which has not been maintained for a long time.

However, Trove team is not going to migrate all the existing functional tests to `trove-tempest-plugin <https://github.com/openstack/trove-tempest-plugin>`_ due to lack of upstream maintainers, new functional tests should go with trove-tempest-plugin, new features shouldn't break the existing functional tests.

.. note::

   In this guide, "functional test" refers to the existing functional test cases in trove repo, "tempest test" refers to test cases in trove-tempest-plugin repo.

Since Victoria, the upstream CI jobs keep failing because of the poor performance of the CI devstack host (virtual machine), trove project contributors should guarantee any proposed patch passes both the functional test and trove tempest test by themselves, the code reviewer may ask for the test result.

.. note::

    Since Caracal, functional test are removed from Trove project.

Install DevStack
----------------

It's recommended that the DevStack host should support nested virtualization, otherwise errors or timeouts may occur during the testing. Refer to https://docs.openstack.org/devstack/latest/guides/devstack-with-nested-kvm.html for how to check and enable nested virtualization on the host.

See :ref:`Install Trove in DevStack <install_devstack>` for development environment installation.

Run functional test (outdated)
------------------------------

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

Run tempest test in DevStack
----------------------------

Trove tempest test can be running in the same way as other openstack tempest test. See `Tempest user guide <https://docs.openstack.org/tempest/latest/overview.html#quickstart>`_.

Devstack installation process will create minimal required changes to ``tempest/etc/tempest.conf``, but you also can modify it as you need. An example config:

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

You can find all available configuration options `here <https://github.com/openstack/trove-tempest-plugin/blob/master/trove_tempest_plugin/config.py>`_.

To run tempest command, you need prepare your env:

    .. code-block:: console

        source .tox/tempest/bin/activate

Or you can put it in your .bashrc:

    .. code-block:: console

        echo "source /opt/stack/tempest/.tox/tempest/bin/activate" >> /opt/stack/.bashrc

Some example commands:

#. List all the MySQL related test cases:

   .. code-block:: console

      tempest run --list-tests --regex ^trove_tempest_plugin | grep -i mysql | sort

#. Run one single test:

   .. code-block:: console

      tempest run --concurrency 1 --regex ^trove_tempest_plugin.tests.scenario.test_replication.TestReplicationMySQL.test_replication
