.. -*- rst -*-

==============================
Database instances (instances)
==============================

Creates, lists, shows details for, attaches a configuration group
to, detaches a configuration group from, deletes, lists
configuration defaults, creates root, and determines whether root
is enables for instances.


Delete database instance
========================

.. rest_method::  DELETE /v1.0/{accountId}/instances/{instanceId}

Deletes a database instance, including any associated data.

This operation does not delete any read slaves.

You cannot complete this operation when the instance state is
either ``REBUILDING`` or ``BUILDING``.

Error response codes:202,413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId
















Show database instance details
==============================

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}

Shows database instance details.

Lists the status and details of the database instance.

Lists the volume size in gigabytes (GB) and the approximate GB
used.

After instance creation, the ``used`` value is greater than 0,
which is expected and due to the automatic creation of non-empty
transaction logs for MySQL optimization. The response does not
include the ``used`` attribute when the instance status is
``BUILD``, ``REBOOT``, ``RESIZE``, or ``ERROR``.

The list operations return a DNS-resolvable host name for the
database instance rather than an IP address. Because the host name
always resolves to the correct IP address for the database
instance, you do not need to maintain the mapping. Although the IP
address might change when you resize, migrate, or perform other
operations, the host name always resolves to the correct database
instance.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-instance-status-detail-response.json
   :language: javascript














Attach configuration group
==========================

.. rest_method::  PUT /v1.0/{accountId}/instances/{instanceId}

Attaches a configuration group to an instance.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - configuration: configuration
   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-attach-config-group-request.json
   :language: javascript


















Detach configuration group
==========================

.. rest_method::  PUT /v1.0/{accountId}/instances/{instanceId}

Detaches a configuration group from an instance.

When you pass in only an instance ID and omit the configuration ID,
this operation detaches any configuration group that was attached
to the instance.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - configuration: configuration
   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-detach-config-group-request.json
   :language: javascript


















Detach replica
==============

.. rest_method::  PATCH /v1.0/{accountId}/instances/{instanceId}

Detaches a replica from its replication source.

If you created an instance that is a replica of a source instance,
you can detach the replica from the source. This can be useful if
the source becomes unavailable. In this case, you can detach the
replica from the source, making the replica a standalone database
instance. You can then take the new standalone instance and create
a new replica of that instance.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - replica_of: replica_of
   - slave_of: slave_of
   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-detach-replica-request.json
   :language: javascript


















Create database instance
========================

.. rest_method::  POST /v1.0/{accountId}/instances

Creates a database instance.

Asynchronously provisions a database instance. You must specify a
flavor and a volume size. The service provisions the instance with
a volume of the requested size, which serves as storage for the
database instance.

 **Notes**

- You can create only one database instance per POST request.

- You can create a database instance with one or more databases. You
  associate users with each database.

- The default binding for the MySQL instance is port 3306.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - users: users
   - password: password
   - datastore_version: datastore_version
   - name: name
   - flavorRef: flavorRef
   - characterSet: characterSet
   - replica_count: replica_count
   - instance: instance
   - collate: collate
   - databases: databases
   - datastore: datastore
   - configuration: configuration
   - type: type
   - replica_of: replica_of
   - size: size
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-create-instance-request.json
   :language: javascript



Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - updated: updated
   - name: name
   - created: created
   - characterSet: characterSet
   - instance: instance
   - collate: collate
   - databases: databases
   - flavor: flavor
   - users: users



Response Example
----------------

.. literalinclude:: samples/db-create-instance-response.json
   :language: javascript














List database instances
=======================

.. rest_method::  GET /v1.0/{accountId}/instances

Lists information, including status, for all database instances.

Lists status and information for all database instances.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-instances-index-response.json
   :language: javascript














List configuration defaults
===========================

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}/configuration

Lists the configuration defaults for an instance.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-list-cfg-defaults-response.json
   :language: javascript













