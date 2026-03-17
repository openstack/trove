=======================
Trove network isolation
=======================

.. _network_isolation:

Isolate bussiness network from management network
-------------------------------------------------

This document aims to help administrator to configure network_isolation in trove.

Since ``Bobcat`` release, trove adds a new configure option ``network_isolation`` to configure network isolation.

Requirements
------------

For the network isolation feature to operate, verify the following:

* Messaging (RabbitMQ) connectivity works through the Trove management interface.

* Pulling Docker images from the registry works through the Trove management interface.

Network Isolation modes comparison
----------------------------------

With ``network_isolation = False`` mode the Trove guest instance
keeps the network configuration provided by the compute service.

* The guest VM retains the client (tenant) network interface.
* The VM has a normal routing configuration, including a default route if provided by the network.
* The database engine runs inside a Docker container.
* Docker uses its default bridge/NAT networking:
* the container runs in a private Docker network
* ports are exposed on the guest VM
* iptables rules perform DNAT from the VM interface to the container

Traffic flow:

    client network => guest VM interface => Docker NAT => database container

The database service is reachable through the guest VM address.

With ``network_isolation = True`` mode the Trove guest performs
additional network configuration during startup.

* The guest removes the client (tenant) network interface.
* Only the management network interface remains.
* The guest operates without a default route and without external connectivity.
* The management network is used only for:
    * communication with the Trove control plane
    * access to the container registry
    * instance management operations.

When the database container starts:

* Docker attaches the tenant network interface directly to the container.
* The database container receives the tenant network connectivity.
* The guest VM itself remains isolated from the tenant network.

Traffic flow is separated:

    client network => database container (direct interface)

    management network => guest VM (control plane)

Advantages and disadvantages of network isolation
-------------------------------------------------

Advantages:

* Improved security isolation
* Reduced lateral movement risk
* Clear separation of control and data planes
* Secondary effect of reduced CPU utilization overhead by removing NAT

Disadvantages:

* Higher operational complexity

Configure network isolation
---------------------------

* Setting ``management_networks`` in :file:`/etc/trove/trove.conf`, typically, this is a neutron provider
  network with a gateway configured. see the :ref:`management network <trove-management-network>`

.. path /etc/trove/trove.conf
.. code-block:: ini

    [DEFAULT]
    management_networks = <your-network-id>

* Setting network_isolation to True (default is already True)

.. path /etc/trove/trove.conf
.. code-block:: ini

    [network]
    network_isolation: True

.. note::

    User can disable this feature by setting `network_isolation` to `False`

Debugging with network issue
----------------------------

.. code-block:: console

    ssh -i <your-private-key> <username>@<instance-ip>
    sudo ln -s /var/run/docker/netns/ /var/run/netns
    sudo ip netns
    sudo ip netns exec <netns-id> ip a


Upgrade
-------

This feature is not backward compatible with older Trove guest images; you need to re-build the guest image
with the updated code. see the :ref:`build image <build_guest_images>`