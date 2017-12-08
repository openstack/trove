.. _guest_cloud_init:

.. role:: bash(code)
   :language: bash

===========================
Guest Images via Cloud-Init
===========================

.. If section numbers are desired, unindent this
    .. sectnum::

.. If a TOC is desired, unindent this
    .. contents::

Overview
========

While creating an image is the preferred method for providing a base
for the Guest Instance, there may be cases where creating an image
is impractical. In those cases a Guest instance can be based on
an available Cloud Image and configured at boot via cloud-init.

Currently the most tested Guest image is Ubunutu 14.04 (trusty).

Setting up the Image
====================

* Visit the `Ubuntu Cloud Archive <https://cloud-images.ubuntu.com/trusty/20160816>`_ and download ``trusty-server-cloudimg-amd64-disk1.img``.

* Upload that image to glance, and note the glance ID for the image.

* Cloud-Init files go into the directory set by the ``cloudinit_location``
  configuration parameter, usually ``/etc/trove/cloudinit``. Files in
  that directory are of the format ``[datastore].cloudinit``, for
  example ``mysql.cloudinit``.

* Create a cloud-init file for your datastore and put it into place.
  For this example, it is assumed you are using Ubuntu 16.04, with
  the MySQL database and a Trove Agent from the Pike release. You
  would put this into ``/etc/trove/cloudinit/mysql.cloudinit``.

.. code-block:: console

    #cloud-config
    # For Ubuntu-16.04 cloudimage
    apt_sources:
    - source: "cloud-archive:pike"
    packages:
    - trove-guestagent
    - mysql-server-5.7
    write_files:
    - path: /etc/sudoers.d/trove
      content: |
        Defaults:trove !requiretty
        trove ALL=(ALL) NOPASSWD:ALL
    runcmd:
    - stop trove-guestagent
    - cat /etc/trove/trove-guestagent.conf /etc/trove/conf.d/guest_info.conf >/etc/trove/trove.conf
    - start trove-guestagent


* If you need to debug guests failing to launch simply append
  the cloud-init to add a user to allow you to login and
  debug the instance.

* When using ``trove-manage datastore_version_update`` to
  define your datastore simply use the Glance ID you have for
  the Trusty Cloud image.

When trove launches the Guest Instance, the cloud-init will install
the Pike Trove Guest Agent and MySQL database, and then adjust
the configuration files and launch the Guest Agent.

