
.. _dashboard:

Install and configure the Trove dashboard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  * Installation of the Trove dashboard for Horizon is straightforward.
    While there packages available for Mitaka, they have a `bug
    <https://bugs.launchpad.net/trove-dashboard/+bug/1580527>`_
    which prevents network selection while creating instances.
    So it is best to install via pip.

   .. code-block:: console

      # pip install trove-dashboard

  * The command above will install the latest version which is
    appropriate if you are running the latest Trove. If you are
    running an earlier version of Trove you may need to specify
    a compatible version of trove-dashboard. 7.0.0.0b2 is known
    to work with the Mitaka release of Trove.

  * After pip installs them locate the trove-dashboard directory and
    copy the contents of the ``enabled/`` directory to your horizon
    ``openstack_dashboard/local/enabled/`` directory.

  * Reload apache to pick up the changes to Horizon.

