=================================
Welcome to Trove's documentation!
=================================

Trove is Database as a Service for OpenStack. It's designed to run
entirely on OpenStack, with the goal of allowing users to quickly and
easily utilize the features of a relational database without the
burden of handling complex administrative tasks. Cloud users and
database administrators can provision and manage multiple database
instances as needed.

Initially, the service will focus on providing resource isolation at
high performance while automating complex administrative tasks
including deployment, configuration, patching, backups, restores, and
monitoring.

For an in-depth look at the project's design and structure, see the
:doc:`contributor/design` page.

.. toctree::
   :maxdepth: 2

   install/index
   user/index
   admin/index
   cli/index
   contributor/index
   reference/index


* Source Code Repositories

  - `Trove`_
  - `Trove Client`_

* `Trove Wiki`_ on OpenStack
* `Trove API Documentation`_ on developer.openstack.org


Guest Images
============

In order to use Trove, you need to have Guest Images for each
datastore and version. These images are loaded into Glance and
registered with Trove.

For those wishing to develop guest images, please refer to the
:ref:`build_guest_images` page.


Search Trove Documentation
==========================

* :ref:`search`


.. _Trove Wiki: https://wiki.openstack.org/wiki/Trove
.. _Trove: https://git.openstack.org/cgit/openstack/trove
.. _Trove Client: https://git.openstack.org/cgit/openstack/python-troveclient
.. _Trove API Documentation: http://developer.openstack.org/api-ref/database/
