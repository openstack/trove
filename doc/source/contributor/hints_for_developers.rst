.. _hints_for_developers:

===========================
Hints & tips for Developers
===========================

Checking Trove instances
~~~~~~~~~~~~~~~~~~~~~~~~

Trove creates compute instance in service project for each database
instance. To see compute instance ID, you can run from admin account:

.. code-block:: console

    openstack database instance show -c server_id <instance id>

You can see all trove servers in service project with command:

.. code-block:: console

    openstack server list --project service
    openstack server show <server id>

To remove database instance which is stuck in "BUILD" status, you may
reset the status and then gracefully remove it using commands:

.. code-block:: console

    openstack database instance reset status <id>
    openstack database instance delete <id>

Logging and Debugging
~~~~~~~~~~~~~~~~~~~~~

Using test resources
--------------------

Each test run creates required resources and deletes them afterwards.
In the cases when database instance create process fails, you may
require to inspect what's wrong. You can stop a running test scenario
using ``Ctrl+C`` in the middle, resources will not be deleted and you
manually ssh into the test instance for inspection. To find the
instance IP address, see ``openstack server list`` output. The
instance management IP is located in the trove-mgmt network. SSH
login as ``ubuntu@ip`` and then use ``sudo``.


Restarting services
-------------------

When you modify server-side code, for trove taskmanager, trove api or
trove conductor, you need to restart corresponding services. When
running Trove in a DevStack environment, you need to restart the
corresponding services:

.. code-block:: console

    sudo systemctl restart devstack@tr-tmgr.service # trove taskmanager
    sudo systemctl restart devstack@tr-cond.service # trove conductor
    sudo systemctl restart apache2 # trove api

Checking logs
-------------

Commands to check and follow logs on server-side:

.. code-block:: console

    sudo journalctl -u devstack@tr-tmgr -n 100 -f
    sudo journalctl -u devstack@tr-cond -n 100 -f
    sudo less /var/log/apache2/trove-api.log -f

Command to check logs in guest instance:

.. code-block:: console

    less /var/log/trove/trove-guestagent.log -f

.. note::

    You can press ``Ctrl + C`` to quit following mode in less and
    press ``Shift + F`` to enter following mode.

Docker-related commands
-----------------------

See all docker containers including stopped:

.. code-block:: console

    sudo docker ps -a

Output logs of database container (sometimes extremely useful):

.. code-block:: console

    docker logs database -f

Output logs of backup container:

.. code-block:: console

    docker logs db_backup -f

To see container details: mounts, networks, etc...:

.. code-block:: console

    docker inspect database

Debugging guestagent
--------------------

When you need to modify and debug code in the guestagent, you can
quickly propagate it inside database instance and check the result,
without recreating it. You need ssh into the instance and then run:

.. code-block:: console

   sudo rm /home/ubuntu/trove-installed && sudo systemctl restart guest-agent

Testing
~~~~~~~

You can significantly increase test execution speed by using the
``--concurrency`` flag. For example:

.. code-block:: console

    tempest run --concurrency 6 trove_tempest_plugin

.. warning::

    By default, ``--concurrency`` is equal to the number of CPUs in
    your system. This may overload the system and produce false
    negative results. It is recommended to use a lower value.
    For example half of the available CPUs would be a good start to
    play with, later you can find out the optimal value
    experimentally.

Running tests in working setups
-------------------------------

When running tests against a real OpenStack deployment, ensure that
sufficient resources are available. For example, check the number of
free floating IPs, security groups and instance quota, and the total
available volume capacity.

Testing constraints
-------------------

Two major features significantly affect internal behavior:
    - Backup/snapshot storage strategy: Swift or Cinder, see
      :ref:`backups area section <backup_db>`
    - Network isolation: enabled or disabled, see
      :ref:`network isolation section <network_isolation>`

When implementing a new feature, verify that it works with all
possible combinations of these settings:

+--------------------------+-------------------------+------------------------+
|                          | network_isolation=False | network_isolation=True |
+==========================+=========================+========================+
| storage_strategy=cinder  |        works ✔          |        works ✔         |
+--------------------------+-------------------------+------------------------+
| storage_strategy=swift   |        works ✔          |        works ✔         |
+--------------------------+-------------------------+------------------------+

.. note::

    Feel free to add more hints in this section which may help
    developers to increase their productivity.
