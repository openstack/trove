.. -*- rst -*-

=====================
Databases (databases)
=====================

Creates, lists all, and deletes databases.


Delete database
===============

.. rest_method::  DELETE /v1.0/{accountId}/instances/{instanceId}/databases/{databaseName}

Deletes a database.

This operation also deletes all data that is associated with the
database.

Normal response codes: 202
Error response codes: badRequest(400),unauthorized(401),forbidden(403),itemNotFound(404),
badMethod(405), overLimit(413),unprocessableEntity(422),instanceFault(500),notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - databaseName: databaseName
   - accountId: accountId
















Create database
===============

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/databases

Creates a database within an instance.

Normal response codes: 202
Error response codes: badRequest(400),unauthorized(401),forbidden(403),itemNotFound(404),
badMethod(405),overLimit(413),unprocessableEntity(422),instanceFault(500),notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - characterSet: characterSet
   - collate: collate
   - name: name
   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-create-databases-request.json
   :language: javascript

















List instance databases
=======================

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}/databases

Lists databases for an instance.

This operation returns only the user-defined databases and not the
system databases. Only the database administrator can view the
``mysql``, ``information_schema``, and ``lost+found`` system
databases.


Normal response codes: 200
Error response codes: badRequest(400),unauthorized(401),forbidden(403),itemNotFound(404),
badMethod(405),overLimit(413),unprocessableEntity(422),instanceFault(500),notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-list-databases-response.json
   :language: javascript













