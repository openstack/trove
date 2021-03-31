.. _trove-config-file:

-------------------------------
Trove Sample Configuration File
-------------------------------

Configure Trove by editing /etc/trove/trove.conf.

No config file is provided with the source code, it will be created during
the installation. In case where no configuration file was installed, one
can be easily created by running::

    tox -e genconfig


To see configuration options available, please refer to :ref:`trove-conf`.

.. only:: html

   The following is a sample Trove configuration for adaptation and use.
   It is auto-generated from Trove when this documentation is built, and
   can also be viewed in `file form <../_static/trove.conf.sample>`_.

   .. literalinclude:: ../_static/trove.conf.sample
