.. -*- rst -*-

============
API versions
============

Lists information for all Database Service API versions and shows
Database Service v1.0 details.


List versions
~~~~~~~~~~~~~

.. rest_method::  GET /

Lists information about all Database Service API versions.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Response Example
----------------

.. literalinclude:: samples/db-versions-response.json
   :language: javascript




Show version details
~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0

Shows details for the Database Service API v1.0.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Response Example
----------------

.. literalinclude:: samples/db-version-response.json
   :language: javascript
