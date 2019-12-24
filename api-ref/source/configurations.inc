.. -*- rst -*-

====================
Configuration groups
====================




List configuration groups
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/configurations

Lists all configuration groups.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id


Response Example
----------------

.. literalinclude:: samples/config-groups-list-response.json
   :language: javascript




Create configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/configurations

Creates a configuration group.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore: datastore
   - name: name
   - values: values


Request Example
---------------

.. literalinclude:: samples/config-group-create-request.json
   :language: javascript


Response Example
----------------

.. literalinclude:: samples/config-group-create-response.json
   :language: javascript




Show configuration group details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/configurations/{configId}

Lists details about a configuration group, including its values.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - configId: configId


Response Example
----------------

.. literalinclude:: samples/config-group-show-response.json
   :language: javascript




List instances applied the configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/configurations/{configId}/instances

Lists the instances associated with the specified configuration group.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - configId: configId


Response Example
----------------

.. literalinclude:: samples/config-group-list-instances-response.json
   :language: javascript




Patch configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{project_id}/configurations/{configId}

Sets new values for a configuration group.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - configId: configId
   - values: values


Request Example
---------------

.. literalinclude:: samples/config-group-patch-request.json
   :language: javascript




Update configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/configurations/{configId}

Sets new values for a configuration group. Also lets you change the name and
description of the configuration group.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - configId: configId
   - values: values
   - description: description
   - name: name


Request Example
---------------

.. literalinclude:: samples/config-group-put-request.json
   :language: javascript




Delete configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/configurations/{configId}

Deletes a configuration group.

Normal response codes: 202


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - configId: configId