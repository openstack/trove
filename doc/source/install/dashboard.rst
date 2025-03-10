
.. _dashboard:

Install and configure the Trove dashboard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Installation of the Trove dashboard for Horizon is straightforward.
  It is best to install it via pip.

  .. code-block:: console

     # python3 -m pip install trove-dashboard

* The command above will install the latest version which is
  appropriate if you are running the latest Trove. If you are
  running an earlier version of Trove you may need to specify
  a compatible version of trove-dashboard.

* After pip installs it, locate the trove-dashboard directory (approximate path: /usr/local/lib/python3.XX/site-packages/) and
  copy the contents of the ``enabled/`` directory to your horizon
  ``openstack_dashboard/local/enabled/`` directory.

* If your use Ubuntu, reload Apache to pick up the changes to Horizon:

  .. code-block:: console

     # systemctl reload apache2.service

* If your use RHEL/CentOS, restart Apache to pick up the changes to Horizon:

  .. code-block:: console

     # systemctl restart httpd.service
