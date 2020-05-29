.. _database:

=========
Datastore
=========

The Database service provides database management features.

Introduction
~~~~~~~~~~~~

The Database service provides scalable and reliable cloud
provisioning functionality for both relational and non-relational
database engines. Users can quickly and easily use database features
without the burden of handling complex administrative tasks. Cloud
users and database administrators can provision and manage multiple
database instances as needed.

The Database service provides resource isolation at high performance
levels, and automates complex administrative tasks such as deployment,
configuration, patching, backups, restores, and monitoring.

Create datastore
~~~~~~~~~~~~~~~~

An administrative user can create datastores for a variety of databases.

This section assumes you do not yet have a MySQL data store, and shows
you how to create a MySQL data store and populate it with a MySQL 5.5
data store version.

.. note::

    From Victoria release, all the datastores can be configured with a same
    Glance image but with different datastore name and version number.

**To create a data store**

#. **Create a trove image**

   Refer to `Build images using trovestack
   <https://docs.openstack.org/trove/latest/admin/building_guest_images.html#build-images-using-trovestack>`_

#. **Register image with Image service**

   You need to register your guest image with the Image service as cloud admin.

   .. code-block:: console

      openstack image create \
        trove-guest-ubuntu-bionic \
        --private \
        --disk-format qcow2 --container-format bare \
        --file $image_file \
        --property hw_rng_model='virtio' \
        --tag trove

#. **Create the datastore**

   Create the data store that configured with the new image. To do this, use
   the :command:`trove-manage` :command:`datastore_update` command.

   This example uses the following arguments:

   .. list-table::
      :header-rows: 1
      :widths: 20 20 20

      * - Argument
        - Description
        - In this example:
      * - config file
        - The configuration file to use.
        - ``--config-file=/etc/trove/trove.conf``
      * - name
        - Name you want to use for this data store.
        - ``mysql``
      * - default version
        - You can attach multiple versions/images to a data store. For
          example, you might have a MySQL 5.5 version and a MySQL 5.6
          version. You can designate one version as the default, which
          the system uses if a user does not explicitly request a
          specific version.
        - ``""``

          At this point, you do not yet have a default version, so pass
          in an empty string.

   |

   Example:

   .. code-block:: console

      $ trove-manage --config-file=/etc/trove/trove.conf datastore_update mysql ""

#. **Add a version to the new data store**

   Now that you have a MySQL data store, you can add a version to it,
   using the :command:`trove-manage` :command:`datastore_version_update`
   command. The version indicates which guest image to use.

   This example uses the following arguments:

   .. list-table::
      :header-rows: 1
      :widths: 20 20 20

      * - Argument
        - Description
        - In this example:

      * - config file
        - The configuration file to use.
        - ``--config-file=/etc/trove/trove.conf``

      * - data store
        - The name of the data store you just created via
          ``trove-manage`` :command:`datastore_update`.
        - ``mysql``

      * - version name
        - The name of the version you are adding to the data store.
        - ``mysql-5.5``

      * - data store manager
        - Which data store manager to use for this version. Typically,
          the data store manager is identified by one of the following
          strings, depending on the database:

          * cassandra
          * couchbase
          * couchdb
          * db2
          * mariadb
          * mongodb
          * mysql
          * percona
          * postgresql
          * pxc
          * redis
          * vertica
        - ``mysql``

      * - glance ID
        - The ID of the guest image you just added to the Image
          service. You can get this ID by using the glance
          :command:`image-show` IMAGE_NAME command.
        - bb75f870-0c33-4907-8467-1367f8cb15b6

      * - packages
        - If you want to put additional packages on each guest that
          you create with this data store version, you can list the
          package names here.
        - ``""``

          In this example, the guest image already contains all the
          required packages, so leave this argument empty.

      * - active
        - Set this to either 1 or 0:
           * ``1`` = active
           * ``0`` = disabled
        - 1

   |

   Example:

   .. code-block:: console

      $ trove-manage --config-file=/etc/trove/trove.conf datastore_version_update mysql mysql-5.5 mysql GLANCE_ID "" 1

   **Optional.** Set your new version as the default version. To do
   this, use the :command:`trove-manage` :command:`datastore_update`
   command again, this time specifying the version you just created.

   .. code-block:: console

      $ trove-manage --config-file=/etc/trove/trove.conf datastore_update mysql mysql-5.5

#. **Load validation rules for configuration groups**

   **Background.** You can manage database configuration tasks by using
   configuration groups. Configuration groups let you set configuration
   parameters, in bulk, on one or more databases.

   When you set up a configuration group using the :command:`openstack database
   configuration create` command, this command compares the configuration
   values you are setting against a list of valid configuration values that are
   stored in the ``validation-rules.json`` file.

   .. list-table::
      :header-rows: 1
      :widths: 20 20 20

      * - Operating System
        - Location of :file:`validation-rules.json`
        - Notes

      * - Ubuntu 14.04
        - :file:`/usr/lib/python2.7/dist-packages/trove/templates/DATASTORE_NAME`
        - DATASTORE_NAME is the name of either the MySQL data store or
          the Percona data store. This is typically either ``mysql``
          or ``percona``.

      * - RHEL 7, CentOS 7, Fedora 20, and Fedora 21
        - :file:`/usr/lib/python2.7/site-packages/trove/templates/DATASTORE_NAME`
        - DATASTORE_NAME is the name of either the MySQL data store or
          the Percona data store. This is typically either ``mysql`` or ``percona``.

   |

   Therefore, as part of creating a data store, you need to load the
   ``validation-rules.json`` file, using the :command:`trove-manage`
   :command:`db_load_datastore_config_parameters` command. This command
   takes the following arguments:

   * Data store name
   * Data store version
   * Full path to the ``validation-rules.json`` file

   |

   This example loads the ``validation-rules.json`` file for a MySQL
   database on Ubuntu 14.04:

   .. code-block:: console

      $ trove-manage db_load_datastore_config_parameters mysql mysql-5.5 /usr/lib/python2.7/dist-packages/trove/templates/mysql/validation-rules.json

#. **Validate data store**

   To validate your new data store and version, start by listing the
   data stores on your system:

   .. code-block:: console

      $ openstack datastore list
      +--------------------------------------+--------------+
      |                  id                  |     name     |
      +--------------------------------------+--------------+
      | 10000000-0000-0000-0000-000000000001 | Legacy MySQL |
      | e5dc1da3-f080-4589-a4c2-eff7928f969a |    mysql     |
      +--------------------------------------+--------------+

   Show the versions of a specific datastore:

   .. code-block:: console

      $ openstack datastore version list mysql
      +--------------------------------------+-----------+
      |                  id                  |    name   |
      +--------------------------------------+-----------+
      | 36a6306b-efd8-4d83-9b75-8b30dd756381 | mysql-5.5 |
      +--------------------------------------+-----------+
