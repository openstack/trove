===========================
 Enabling Trove in DevStack
===========================

To enable Trove in DevStack, perform the following steps:

::

    Note: The python-troveclient is automatically installed.  If you need to
    control how the client gets installed, set the TROVECLIENT_REPO,
    TROVECLIENT_DIR and TROVECLIENT_BRANCH environment variables appropriately.


Download DevStack
=================

.. code-block:: bash

    export DEVSTACK_DIR=~/devstack
    git clone https://opendev.org/openstack/devstack.git $DEVSTACK_DIR

Enable the Trove plugin
=======================

Enable the plugin by adding the following section to
``$DEVSTACK_DIR/local.conf``

.. code-block:: bash

     [[local|localrc]]
     enable_plugin trove https://opendev.org/openstack/trove

Optionally, a git refspec (branch or tag or commit) may be provided as follows:

.. code-block:: bash

     [[local|localrc]]
     enable_plugin trove https://opendev.org/openstack/trove <refspec>

Run the DevStack utility
========================

.. code-block:: bash

     cd $DEVSTACK_DIR
     ./stack.sh
