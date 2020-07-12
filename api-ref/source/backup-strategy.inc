.. -*- rst -*-

===============
Backup Strategy
===============

Backup strategy allows the user to customize the way of creating backups. Users
can create strategy either in the project scope or for a particular database
instance.


List backup strategies
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/backup_strategies

List backup strategies for a project. You can filter the results by
using query string parameters. The following filters are supported:

- ``instance_id={instance_id}`` - Return the list of backup strategies for a
  particular database instance.
- ``project_id={project_id}`` - Return the list of backup strategies for a
  particular project, admin only.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - backup_strategies: backup_strategy_list
    - project_id: project_id
    - instance_id: instanceId1
    - backend: backup_backend
    - swift_container: swift_container_required

Response Example
----------------

.. literalinclude:: samples/backup-strategy-list-response.json
   :language: javascript


Create backup strategy
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/backup_strategies

Creates or updates backup strategy for the project or a database instance.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instance_id: instance_id_optional
   - swift_container: swift_container_required

Request Example
---------------

.. literalinclude:: samples/backup-strategy-create-request.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - project_id: project_id
    - instance_id: instanceId1
    - backend: backup_backend
    - swift_container: swift_container_required

Response Example
----------------

.. literalinclude:: samples/backup-strategy-create-response.json
   :language: javascript


Delete database strategy
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/backup_strategies

Deletes a database strategy for a project. If ``instance_id`` is specified in
the URL query parameters, delete the database strategy for that particular
database instance. Additionally, admin user is allowed to delete backup
strategy of other projects by specifying ``project_id`` in the URL query
parameters.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id