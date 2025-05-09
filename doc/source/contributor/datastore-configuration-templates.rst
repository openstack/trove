=======================================
Trove Datastore Configuration Templates
=======================================

In order to support the injecting of dynamic configuration into database
configuration files Trove uses the Jinja2 templating engine.

A general guide to writing Jinja2 templates can be found at
https://jinja.palletsprojects.com/en/stable/templates/

Location and Searching
======================

The templates used to configure database instances are located under
`trove/templates` with a directory for each database support by Trove.

The Datastore Version is used to determine which set of templates are used. A
set of locations are search in a priority order with the most specific location
that exists used.  The locations search are based upon the Datastore Version
name, version and manager as well as the Datastore name.

For example consider the following layout under `trove/templates`:

.. code-block::

    mysql/
        mysql-test/
            config.template
        5.5/
            config.template
        config.template

If the Datastore Version for `mysql` has the name `mysql-test` then the template
file `mysql/mysql-test/config.template` will be used.

If the Datastore Version for `mysql` has the name `5.5.62` then Trove will look
for `mysql/5.5.62`, then `mysql/5.5`, `mysql/5` and finally `mysql/`.  Based on
the above layout Trove will use `mysql/5.5/config.template`.


Variables available in the templates
====================================

The following variables are exposed to the templates and may be useful in
making the template adapt to different database sizes or versions.

datastore
~~~~~~~~~

Contains details of the Datastore and Datastore Version and has the following
attributes:

``name``
    The Datastore name, for example "mysql", "postgresql" or "MySQL".  It is
    used in locating the template to used as described above.
    The value is set by the operators so may be difficult to rely on in a
    template.

``manager``
    The Datastore Version manager - this is the type of the datastore and
    corresponds to the name used in the Trove code for example "mysql" or
    "postgresql".  See trove/common/constants.py for a list of managers.
    Like `name` it is used in locating templates files.

``version``
    This variable is the value of the Datastore Version name.  Usually it will
    be the release version of the database such as "5.7.30", but can be a string
    like "mysql-test".  The value is configured by the operator.

``semantic_version``
    A parsed version from the Datastore Version version or name.  Trove will first
    attempt to parse the Datastore Version version, then the Datastore Version name.
    The `datastore.semantic_version` makes the components of a version string
    available as attributes `major`, `minor`, `patch`.

    In the following example the major version of a PostgreSQL database is used to
    select between different configuration options for retaining the binary logs

    .. code-block::

        {% if datastore.semantic_version.major >= 13 %}
        wal_keep_size = 80 # in MB = wal_keep_segments x wal_keep_size
        {% else %}
        wal_keep_segments = 5 # in logfile segments; 0 disables
        {% endif %}

flavor
~~~~~~
The flavor variable is a dictionary of the resource sizes of the compute server
that will be hosting the database.  It includes details on the number of VCPUs
and the maximum amount of RAM.

The following example configures the thread cache size for a mysql database
based on the maximum RAM of the server:

.. code-block::

  thread_cache_size = {{ (4 * flavor['ram']/512)|int }}

server_id
~~~~~~~~~

A unique ID based on a hash of the instance ID and it is useful to use in the
configuration of a replication set to distinguish between the primary and
secondary instance.

The following example is from a MySQL configuration template:

.. code-block::

    server_id = {{server_id}}
