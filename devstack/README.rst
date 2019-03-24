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

.. sourcecode:: bash

    export DEVSTACK_DIR=~/devstack
    git clone https://git.openstack.org/openstack-dev/devstack.git $DEVSTACK_DIR

Enable the Trove plugin
=======================

Enable the plugin by adding the following section to ``$DEVSTACK_DIR/local.conf``

.. sourcecode:: bash

     [[local|localrc]]
     enable_plugin trove https://git.openstack.org/openstack/trove

Optionally, a git refspec (branch or tag or commit) may be provided as follows:

.. sourcecode:: bash

     [[local|localrc]]
     enable_plugin trove https://git.openstack.org/openstack/trove <refspec>

Run the DevStack utility
========================

.. sourcecode:: bash

     cd $DEVSTACK_DIR
     ./stack.sh
