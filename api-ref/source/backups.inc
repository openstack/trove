.. -*- rst -*-

=======
Backups
=======

List, show details, create and delete backups.


List database backups
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/backups

List all database backups information for a tenant.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - accountId: accountId


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - backups: backup_list
    - created: created
    - datastore: datastore2
    - datastore.type: datastore_type1
    - datastore.version: datastore_version_name
    - datastore.version_id: datastore_version_id1
    - description: backup_description1
    - id: backup_id
    - instance_id: backup_instanceId
    - locationRef: backup_locationRef
    - name: backup_name
    - parent_id: backup_parentId1
    - size: backup_size
    - status: backup_status
    - updated: updated


Response Example
----------------

.. literalinclude:: samples/db-backup-list-response.json
   :language: javascript




List database backups for an instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}/backups

List all database backups for the specified instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - backups: backup_list
    - created: created
    - datastore: datastore2
    - datastore.type: datastore_type1
    - datastore.version: datastore_version_name
    - datastore.version_id: datastore_version_id1
    - description: backup_description1
    - id: backup_id
    - instance_id: backup_instanceId
    - locationRef: backup_locationRef
    - name: backup_name
    - parent_id: backup_parentId1
    - size: backup_size
    - status: backup_status
    - updated: updated


Response Example
----------------

.. literalinclude:: samples/db-backups-by-instance-response.json
   :language: javascript




Show database backup details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{accountId}/backups/{backupId}

Show detailes of a backup.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - accountId: accountId
   - backupId: backup_id


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - created: created
    - datastore: datastore2
    - datastore.type: datastore_type1
    - datastore.version: datastore_version_name
    - datastore.version_id: datastore_version_id1
    - description: backup_description1
    - id: backup_id
    - instance_id: backup_instanceId
    - locationRef: backup_locationRef
    - name: backup_name
    - parent_id: backup_parentId1
    - size: backup_size
    - status: backup_status
    - updated: updated


Response Example
----------------

.. literalinclude:: samples/db-backup-get-response.json
   :language: javascript




Create database backup
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{accountId}/backups

Creates a database backup for instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - name: backup_name
   - instance: backup_instanceId
   - parent_id: backup_parentId
   - incremental: backup_incremental
   - description: backup_description
   - accountId: accountId


Request Example
---------------

.. literalinclude:: samples/db-backup-create-request.json
   :language: javascript


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - created: created
    - datastore: datastore2
    - datastore.type: datastore_type1
    - datastore.version: datastore_version_name
    - datastore.version_id: datastore_version_id1
    - description: backup_description1
    - id: backup_id
    - instance_id: backup_instanceId
    - locationRef: backup_locationRef
    - name: backup_name
    - parent_id: backup_parentId1
    - size: backup_size
    - status: backup_status
    - updated: updated


Response Example
----------------

.. literalinclude:: samples/db-backup-create-response.json
   :language: javascript




Delete database backup
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{accountId}/backups/{backupId}

Deletes a database backup.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - backupId: backup_id
   - accountId: accountId
