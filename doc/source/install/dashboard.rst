
.. _dashboard:

Install and configure the Trove dashboard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  * Installation of the Trove dashboard for Horizon is straightforward.
    It is best to install it via pip.

   .. code-block:: console

      # pip install trove-dashboard

  * The command above will install the latest version which is
    appropriate if you are running the latest Trove. If you are
    running an earlier version of Trove you may need to specify
    a compatible version of trove-dashboard.

  * After pip installs it, locate the trove-dashboard directory and
    copy the contents of the ``enabled/`` directory to your horizon
    ``openstack_dashboard/local/enabled/`` directory.

  * Reload Apache to pick up the changes to Horizon.

