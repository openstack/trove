===============
Troubleshooting
===============

Instance stuck in BUILD status
------------------------------

The possible reasons for this issue:

* Networking issue between message queue service(e.g. RabbitMQ) and Trove guest
  instance. When creating a Trove instance, trove-taskmanager sends a message
  to the message queue, which is expected to be received and handled by the
  trove-guestagent service which is running inside the instance. The instance
  status should be updated by trove-guestagent service after handling.
  Apparently, If the trove-guestagent can't connect with RabbitMQ, the
  instance status won't be updated.
* Code bug in trove-guestagent. You should be able to see some error log in
  trove-guestagent log file (by default,
  ``/var/log/trove/trove-guestagent.log``).
* If you are using the dev mode image, it's also possible that trove-guestagent
  can't connect to Trove controller host to download trove-guestagent service
  code, either because of network connectivity issue or the ssh key is missing
  or incorrect.

In either case, you will need to ssh into the Trove instance and check the log.
In order to do that, you need to make sure:

* You have the admin credentials to get the IP address of Trove instance
  management port. The management port is a Neutron port allocated from the
  management network (defined by ``management_networks`` config option). For
  example, you need to log into a Trove instance named 'test', and the
  management network name is 'trove-mgmt', you can run:

  .. code-block:: console

      $ openstack server list | grep test | grep trove-mgmt
      | 810fc014-bd9f-4464-b506-1b78f37c495e | test | ACTIVE | private=10.1.0.57; trove-mgmt=192.168.254.229 | ubuntu-xenial-mysql-5.7-dev | ds1G   |

* The TCP 22 port is allowed in the Neutron security group (defined by
  ``management_security_groups`` config option) that applied to the management
  port.
* You have the SSH private key. The Trove instance should be created using a
  Nova keypair defined by ``nova_keypair`` config option.

After log into the instance, you can check the trove-guestagent log by:

.. code-block:: console

    sudo journalctl -u trove-guest.service | less # or
    sudo vi /var/log/trove/trove-guestagent.log

Please contact Trove team in #openstack-trove IRC channel or send email to
openstack-discuss@lists.openstack.org if help needed.

.. note::

    The Trove instance creation time varies in different environments, the
    default value of ``usage_timeout`` option (3600 seconds) may not be applied
    to all, the cloud administrator should change that based on testing so that
    the instance creation should fail in a reasonable timely manner.
