===========================================
Welcome to Trove's developer documentation!
===========================================

Introduction
============

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
:doc:`dev/design` page.


Installation And Deployment
===========================

Trove is constantly under development. The easiest way to install
Trove is using the Trove integration scripts that can be found in
github in the `Trove Integration`_ Repository.

For further details on how to install Trove using the integration
scripts please refer to the :doc:`dev/install` page.

For further details on how to install Trove to work with existing
OpenStack environment please refer to the :doc:`dev/manual_install` page.

Developer Resources
===================

For those wishing to develop Trove itself, or to extend Trove's
functionality, the following resources are provided.

.. toctree::
  :maxdepth: 1

  dev/design
  dev/install
  dev/manual_install.rst

* Source Code Repositories

  - `Trove`_
  - `Trove Integration`_
  - `Trove Client`_

* `Trove Wiki`_ on OpenStack
* `Trove API Documentation`_ on github


Search Trove Documentation
==========================

* :ref:`search`


.. _Trove Wiki: https://wiki.openstack.org/wiki/Trove
.. _Trove: https://www.github.com/openstack/trove
.. _Trove Integration: https://www.github.com/openstack/trove-integration
.. _Trove Client: https://www.github.com/openstack/python-troveclient
.. _Trove API Documentation: https://github.com/openstack/database-api/blob/master/openstack-database-api/src/markdown/database-api-v1.md
