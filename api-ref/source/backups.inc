.. -*- rst -*-

=======
Backups
=======




List database backups
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/backups

List all database backups information for a project. You can filter results by
using query string parameters. The following filters are supported:

- ``instance_id={instance_id}`` - Return the list of backups for a particular
  database instance.
- ``all_projects=True/False`` - Return the list of backups for all the
  projects, this is an admin only param by default.
- ``datastore={datastore}`` - Return a list of backups of the same datastore.
- ``project_id={project_id}`` - Get backups of a specific project. Admin
  required.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id


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
    - project_id: project_uuid
    - storage_driver: storage_driver


Response Example
----------------

.. literalinclude:: samples/backup-list-response.json
   :language: javascript




Create database backup
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/backups

Creates a database backup for instance.

In the Trove deployment with service tenant enabled, The backup data is
stored as objects in OpenStack Swift service in the user's container. If not
specified, the container name is defined by the cloud admin.

The user can create a backup strategy within the project scope or specific to
a particular instance.

In multi-region deployment with geo-replicated Swift, the user can also restore
a backup in a region by manually specifying the backup data location created in
another region, then create instances from the backup. Instance ID is not
required in this case.

.. warning::

   The restored backup is dependent on the original backup data, if the
   original backup is deleted, the restored backup is invalid.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - name: backup_name
   - instance: backup_instanceId
   - parent_id: backup_parentId
   - incremental: backup_incremental
   - description: backup_description
   - swift_container: swift_container
   - restore_from: backup_restore_from
   - storage_driver: storage_driver

Request Example
---------------

.. literalinclude:: samples/backup-create-request.json
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
    - project_id: project_uuid
    - storage_driver: storage_driver


Response Example
----------------

.. literalinclude:: samples/backup-create-response.json
   :language: javascript




Show database backup details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/backups/{backupId}

Show detailes of a backup.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
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
    - project_id: project_uuid
    - storage_driver: storage_driver


Response Example
----------------

.. literalinclude:: samples/backup-get-response.json
   :language: javascript




Delete database backup
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/backups/{backupId}

Deletes a database backup. All the child backups are deleted automatically when
a parent backup is deleted.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - backupId: backup_id
