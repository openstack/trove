=======================
Trove network isolation
=======================

.. _network_isolation:

Isolate bussiness network from management network
-------------------------------------------------

This document aims to help administrator to configure network_isolation in trove.

Before ``Bobcat`` release, trove didn't isolate the management network from bussiness network, sometimes, this
may cause network performance issue or security issue.

Since ``Bobcat`` release, trove adds a new configure option(network_isolation) to configure network isolation.

network_isolation has the following behaviors and requirements:

* Trove will not check the overlap between management networks cidrs and bussiness networks cidrs anymore.
  as trove allows the same cidrs between management network and bussiness network.

* Cloud administrator must configure the management_networks in config file. Management network is responsible for
  connecting with rabbitMQ, as well as docker registry. Even though you have set network_isolation to true, if your
  management_networks is not configured, Trove will still not plug the network interface into the container.


Configure network isolation
---------------------------

* Setting ``management_networks`` in :file:`/etc/trove/trove.conf`, typically, this is a neutron provider
  network with a gateway configured. see the :ref:`management network <trove-management-network>`

.. path /etc/trove/trove.conf
.. code-block:: ini

    [DEFAULT]
    management_networks = <your-network-id>

* Setting network_isolation to True(default is False)

.. path /etc/trove/trove.conf
.. code-block:: ini

    [network]
    network_isolation: True

Upgrade
-------

This feature is not backward compatible with older Trove guest images; you need to re-build the guest image
with the updated code. see the :ref:`build image <build_guest_images>`