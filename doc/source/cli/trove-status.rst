============
trove-status
============

Synopsis
========

::

  trove-status <category> <command> [<args>]

Description
===========

:program:`trove-status` is a tool that provides routines for checking the
status of a Trove deployment.

Options
=======

The standard pattern for executing a :program:`trove-status` command is::

    trove-status <category> <command> [<args>]

Run without arguments to see a list of available command categories::

    trove-status

Categories are:

* ``upgrade``

Detailed descriptions are below.

You can also run with a category argument such as ``upgrade`` to see a list of
all commands in that category::

    trove-status upgrade

These sections describe the available categories and arguments for
:program:`trove-status`.

Upgrade
~~~~~~~

.. _trove-status-checks:

``trove-status upgrade check``
  Performs a release-specific readiness check before restarting services with
  new code. This command expects to have complete configuration and access
  to databases and services.

  **Return Codes**

  .. list-table::
     :widths: 20 80
     :header-rows: 1

     * - Return code
       - Description
     * - 0
       - All upgrade readiness checks passed successfully and there is nothing
         to do.
     * - 1
       - At least one check encountered an issue and requires further
         investigation. This is considered a warning but the upgrade may be OK.
     * - 2
       - There was an upgrade status check failure that needs to be
         investigated. This should be considered something that stops an
         upgrade.
     * - 255
       - An unexpected error occurred.

  **History of Checks**

  **11.0.0 (Stein)**

  * Checks if any Trove instance with assigned task is running.
    The assigned tasks may fail during the upgrade process due to transient
    unavailability of Trove control plane.
    Upgrade should be postponed until all instances are in the Active state.

