.. -*- rst -*-

==============================
Database instances (instances)
==============================

Lists, shows details for, creates, attaches a configuration group to, detaches
a configuration group from, update the name, upgrade datastore version,
deletes, lists configuration defaults, creates root, and determines whether
root is enabled, for instances.


List database instances
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/instances

Lists information, including status, for all database instances.

Lists status and information for all database instances.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - accountId: accountId


Response Example
----------------

.. literalinclude:: samples/db-instances-index-response.json
   :language: javascript




Show database instance details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}

Shows database instance details.

Lists the status and details of the database instance.

Lists the volume size in gigabytes (GB) and the approximate GB
used.

After instance creation, the ``used`` value is greater than 0, which
is expected as databases may create some basic (non empty) files to
represent an empty schema. The response does not include the ``used``
attribute when the instance status is ``BUILD``, ``REBOOT``,
``RESIZE``, or ``ERROR``.

The list operations return a DNS-resolvable host name for the
database instance rather than an IP address. Because the host name
always resolves to the correct IP address for the database
instance, you do not need to maintain the mapping. Although the IP
address might change when you resize, migrate, or perform other
operations, the host name always resolves to the correct database
instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId


Response Example
----------------

.. literalinclude:: samples/db-instance-status-detail-response.json
   :language: javascript




Create database instance
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{accountId}/instances

Creates a database instance.

Asynchronously provisions a database instance. You must specify a
flavor and a volume size. The service provisions the instance with
a volume of the requested size, which serves as storage for the
database instance.

 **Notes**

- You can create only one database instance per POST request.

- You can create a database instance with one or more databases. You
  can also associate users with each database.

- The port on which the database instance is listening is database
  specific.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


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




Attach configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{accountId}/instances/{instanceId}

Attaches a configuration group to an instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


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
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{accountId}/instances/{instanceId}

Detaches a configuration group from an instance.

When you pass in only an instance ID and omit the configuration ID,
this operation detaches any configuration group that was attached
to the instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


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
~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{accountId}/instances/{instanceId}

Detaches a replica from its replication source.

If you created an instance that is a replica of a source instance,
you can detach the replica from the source. This can be useful if
the source becomes unavailable. In this case, you can detach the
replica from the source, making the replica a standalone database
instance. You can then take the new standalone instance and create
a new replica of that instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


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




Update instance name
~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{accountId}/instances/{instanceId}

Update the instance name.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instance: instance
   - name: instanceName
   - instanceId: instanceId
   - accountId: accountId


Request Example
---------------

.. literalinclude:: samples/db-update-instance-name-request.json
   :language: javascript




Upgrade datastore version
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{accountId}/instances/{instanceId}

Upgrade datastore version.

During datastore version upgrading, the instance status change to ``UPGRADE``,
and changes back to ``ACTIVE`` after upgrading finishes, otherwize changes to
``ERROR`` if the upgrading fails.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instance: instance
   - datastore_version: datastore_version1
   - instanceId: instanceId
   - accountId: accountId


Request Example
---------------

.. literalinclude:: samples/db-upgrade-instance-datastore-version-request.json
   :language: javascript




Delete database instance
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{accountId}/instances/{instanceId}

Deletes a database instance, including any associated data.

This operation does not delete any read slaves.

You cannot complete this operation when the instance state is
either ``REBUILDING`` or ``BUILDING``.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




List configuration defaults
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}/configuration

Lists the configuration defaults for an instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId


Response Example
----------------

.. literalinclude:: samples/db-list-cfg-defaults-response.json
   :language: javascript
