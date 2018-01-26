.. -*- rst -*-

=====================================
Configuration groups (configurations)
=====================================

Creates and lists all configuration groups.


Create configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{accountId}/configurations

Creates a configuration group.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - datastore: datastore
   - values: values
   - name: name
   - accountId: accountId


Request Example
---------------

.. literalinclude:: samples/db-create-config-group-request.json
   :language: javascript


Response Example
----------------

.. literalinclude:: samples/db-create-config-group-response.json
   :language: javascript




List configuration groups
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/configurations

Lists all configuration groups.

The list includes the associated data store and data store version
for each configuration group.

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

.. literalinclude:: samples/db-list-cfg-groups-response.json
   :language: javascript




List configuration group instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/configurations/{configId}/instances

Lists the instances associated with the specified configuration group.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - configId: configId
   - accountId: accountId


Response Example
----------------

.. literalinclude:: samples/db-config-group-instances-response.json
   :language: javascript




Delete configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{accountId}/configurations/{configId}

Deletes a configuration group.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - configId: configId
   - accountId: accountId




Patch configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{accountId}/configurations/{configId}

Sets new values for a configuration group.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - values: values
   - configId: configId
   - accountId: accountId


Request Example
---------------

.. literalinclude:: samples/db-patch-config-group-request.json
   :language: javascript


Response Example
----------------

.. literalinclude:: samples/db-patch-config-group-response-json-http.txt
   :language: javascript




Show configuration group details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/configurations/{configId}

Lists details about a configuration group, including its values.


Normal response codes: 200
Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - configId: configId
   - accountId: accountId


Response Example
----------------

.. literalinclude:: samples/db-config-group-details-response.json
   :language: javascript




Update configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{accountId}/configurations/{configId}

Sets new values for a configuration group. Also lets you change the name and
description of the configuration group.

Normal response codes: 202
Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - values: values
   - description: description
   - name: name
   - configId: configId
   - accountId: accountId


Request Example
---------------

.. literalinclude:: samples/db-update-config-group-request.json
   :language: javascript
