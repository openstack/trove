.. _database:

=========
Datastore
=========

Introduction
~~~~~~~~~~~~

Admin user needs to create datastore and its versions as required.

A datastore is typically created as a type of database, e.g. the cloud admin
could create 2 datastores for MySQL and PostgreSQL, separately. For each
datastore, there could be multiple datastore versions. For example, for MySQL
database, Trove could support 5.7.29, 5.7.30 or 5.8, etc.

.. note::

   Starting from Victoria, the datastore version number must be the same with
   the image tag of the specific database. To support MySQL 5.7.29, a new
   datastore version with version number 5.7.29 based on `mysql docker image
   <https://hub.docker.com/_/mysql?tab=tags&name=5.7.29>`_ needs to be created.

A datastore version is always associated with a Glance image, either by image
ID or image tags. If the image ID is not provided, the image can be retrieved
by the image tags. The tags are used for filtering as a whole rather than
separately. Using image tags is more flexible than ID especially when a new
guest image is uploaded to Glance, Trove can pick up the latest image
automatically for creating instances.

Create datastore version
~~~~~~~~~~~~~~~~~~~~~~~~

When creating a datastore version, Trove will create the datastore first if it
doesn't exist. Different datastore versions can have the same name but
different version numbers, or same version number but different names.

When using image tags, make sure the image with the tags exists before creating
the datastore version.

.. note::

    From Victoria release, all the datastores can be configured with a same
    Glance image but with different datastore name and version name.

To create a datastore version:

#. Create a trove guest image

   Refer to `Build images using trovestack
   <https://docs.openstack.org/trove/latest/admin/building_guest_images.html#build-images-using-trovestack>`_

#. Register image with Image service

   You need to register your guest image with the Image service as cloud admin.
   In this example, the image is assigned tags that will be used when creating
   datastore version.

   .. code-block:: console

      openstack image create \
        trove-guest-ubuntu-bionic \
        --private \
        --disk-format qcow2 --container-format bare \
        --file $image_file \
        --property hw_rng_model='virtio' \
        --tag trove --tag mysql

#. Create the datastore version

   .. code-block:: console

      openstack datastore version create 5.7.29 mysql mysql "" \
        --image-tags trove,mysql \
        --active --default \
        --version-number 5.7.29

#. Load validation rules for configuration groups

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

      * - Ubuntu 18.04
        - :file:`/usr/lib/python3/dist-packages/trove/templates/DATASTORE_NAME`
        - DATASTORE_NAME is the name of the datastore, e.g. ``mysql``
          or ``postgresql``.

      * - RHEL 7, CentOS 7, Fedora 20, and Fedora 21
        - :file:`/usr/lib/python3/site-packages/trove/templates/DATASTORE_NAME`
        - DATASTORE_NAME is the name of the datastore, e.g. ``mysql``
          or ``postgresql``.

   |

   Therefore, as part of creating a data store, you need to load the
   ``validation-rules.json`` file, using the :command:`trove-manage`
   :command:`db_load_datastore_config_parameters` command on trove controller
   node. This command takes the following arguments:

   * Data store name
   * Data store version
   * Full path to the ``validation-rules.json`` file

   |

   This example loads the ``validation-rules.json`` file for a MySQL
   database on Ubuntu 18.04:

   .. code-block:: console

      $ trove-manage db_load_datastore_config_parameters mysql 5.7.29 /usr/lib/python3/dist-packages/trove/templates/mysql/validation-rules.json

Hide a datastore version
~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes, it's needed to make a datastore version invisible to the cloud
users, e.g when a datastore version is deprecated or creating a datastore
version for testing purpose, to do that:

.. code-block:: console

   $ openstack datastore version set <version-id> --disable

Replace image ID with tags
~~~~~~~~~~~~~~~~~~~~~~~~~~

For datastore versions that are created using image ID, it's easy to switch to
image tags without affecting the existing instances. New instances will be
created by the image ID (the most recently uploaded) that getting from Glance
using image tags. To do that, as the cloud admin user:

.. code-block:: console

   $ openstack datastore version set <version-id> --image-tags trove,mysql

Ignoring ``--image`` means removing the image ID from the datastore version if
it's associated.
