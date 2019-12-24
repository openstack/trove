.. -*- rst -*-

=====
Users
=====



Create user
~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/users

Creates users for a database instance.

When specifying user name and password, you can also specify databases that the user can access.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/user-create-request.json
   :language: javascript




List database instance users
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/users

Lists the users in a database instance and the associated databases for that
user.

This operation does not return system users. A system user is a
database administrator who administers the health of the database.
Also, this operation returns the ``root`` user only if it is
enabled.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Example
----------------

.. literalinclude:: samples/user-list-response.json
   :language: javascript




Show database instance user
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/users/{user_name}

Get a specific user information in an instance.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - user_name: user_name


Response Example
----------------

.. literalinclude:: samples/user-show-response.json
   :language: javascript




Delete user
~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/instances/{instanceId}/users/{user_name}

Deletes a user for a database instance.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - user_name: user_name




Update a user
~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}/users/{user_name}

Modify attributes(e.g. user name, allowed host, password) for a specific user.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - user_name: user_name

Request Example
---------------

.. literalinclude:: samples/user-put-request.json
   :language: javascript




Update users passwords
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}/users

Modify passwords for users.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/users-put-request.json
   :language: javascript




Show root-enabled status for database instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/root

Shows root-enabled status for a database instance.

Returns ``true`` if root user is enabled for a database instance.
Otherwise, returns ``false``.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Example
----------------

.. literalinclude:: samples/user-check-root-response.json
   :language: javascript




Enable root user
~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/root

Enables the root user for a database instance and returns the root password.

This operation generates a root password for the root user and
enables the root user to log in from any host.

Enabling root user should only be restricted to admin user， as with root user,
the cloud user can change the database settings, e.g. remove users which
bypassing the Trove API.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Example
----------------

.. literalinclude:: samples/user-enable-root-response.json
   :language: javascript




Disable root user
~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/instances/{instanceId}/root

Disables the root user.

Normal response codes: 204


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId




Show root-enabled history for database instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/mgmt/instances/{instanceId}/root

Admin only API. Show the date and time that root user was enabled(if ever) for
an instance.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Example
----------------

.. literalinclude:: samples/user-show-root-history-response.json
   :language: javascript