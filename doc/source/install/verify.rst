.. _trove-verify:

Verify operation
~~~~~~~~~~~~~~~~

Verify operation of the Database service.

.. note::

   Perform these commands on the node where you installed trove.

#. Source the ``admin`` tenant credentials:

   .. code-block:: console

      $ . admin-openrc

#. Check the ``openstack database instance list`` command should work.

   .. code-block:: console

      $ openstack database instance list

#. Add a datastore to trove:

   * `Create and upload trove guest image <https://docs.openstack.org/trove/latest/admin/building_guest_images.html>`_.
     Create an image for the type of database you want to use, for example,
     MySQL, MariaDB, etc.

   * Create a datastore. You need to create at least one datastore version for
     each type of database supported. This example creates a datastore version
     for MySQL 5.7.29:

     .. code-block:: console

        $ openstack datastore version create 5.7.29 mysql mysql "" \
          --image-tags trove,mysql \
          --active --default

#. Create a database `instance
   <http://docs.openstack.org/user-guide/create_db.html>`_.
