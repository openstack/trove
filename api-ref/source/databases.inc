.. -*- rst -*-

=========
Databases
=========

Currently, the Database and User API is only supported by mysql datastore. For
others, the recommended way is to get root password
(``POST /v1.0/{project_id}/instances/{instance_id}/root``) and communicate with
the database service directly for database and user management.


Create database
~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/databases

Creates a database within an instance.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - name: name
   - characterSet: characterSet
   - collate: collate


Request Example
---------------

.. literalinclude:: samples/databases-create-request.json
   :language: javascript




List instance databases
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/databases

Lists databases for an instance.

This operation returns only the user-defined databases and not the system
databases. Only the database administrator can get system databases such as
``mysql``, ``information_schema``, and ``lost+found``.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Example
----------------

.. literalinclude:: samples/databases-list-response.json
   :language: javascript




List instance databases for a user
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/users/{user_name}/databases

Get all the databases that the user has access to.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - user_name: user_name


Response Example
----------------

.. literalinclude:: samples/databases-list-response.json
   :language: javascript




Grant databases access
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}/users/{user_name}/databases

Grant user access to the databases.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - user_name: user_name


Request Example
---------------

.. literalinclude:: samples/user-grant-databases-access-request.json
   :language: javascript




Revoke databases access
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/instances/{instanceId}/users/{user_name}/databases/{database_name}

Revoke user access to the database.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - user_name: user_name
   - database_name: databaseName




Delete database
~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/instances/{instanceId}/databases/{database_name}

Deletes a database.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - database_name: databaseName