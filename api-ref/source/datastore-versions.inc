.. -*- rst -*-

==================
Datastore Versions
==================




List datastore versions
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/{datastore}/versions

Get all the registered versions for a given datastore

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore: data_store

Response Example
----------------

.. literalinclude:: samples/datastore-version-list-response.json
   :language: javascript




Show datastore version
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/{datastore}/versions/{version}

Get information for a given datastore version(name or ID)

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore: data_store
   - version: version

Response Example
----------------

.. literalinclude:: samples/datastore-version-show-response.json
   :language: javascript




List datastore version configuration parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/{datastore}/versions/{version}/parameters

Get all the config parameters associated with the specified datastore version

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore: data_store
   - version: version

Response Example
----------------

.. literalinclude:: samples/datastore-version-parameter-list-response.json
   :language: javascript




Show datastore version configuration parameter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/{datastore}/versions/{version}/parameters/{parameter_name}

Get the specified config parameter definition.

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore: data_store
   - version: version
   - parameter_name: parameter_name

Response Example
----------------

.. literalinclude:: samples/datastore-version-parameter-show-response.json
   :language: javascript




Show datastore version
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/versions/{datastore_version_id}

Get information for a given datastore version ID.

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id

Response Example
----------------

.. literalinclude:: samples/datastore-version-show-response.json
   :language: javascript




List datastore version configuration parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/versions/{datastore_version_id}/parameters

Get all the config parameters associated with the specified datastore version
ID.

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id

Response Example
----------------

.. literalinclude:: samples/datastore-version-parameter-list-response.json
   :language: javascript



Show datastore version configuration parameter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/versions/{datastore_version_id}/parameters/{parameter_name}

Get the specified config parameter definition.

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id
   - parameter_name: parameter_name

Response Example
----------------

.. literalinclude:: samples/datastore-version-parameter-show-response.json
   :language: javascript



Create datastore version configuration parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/mgmt/datastores/versions/{datastore_version_id}/parameters

Admin only API. Register a configuration parameter for the specified datastore
version. The parameter definition contains the type, minimum and maximum
values(if type is integer), and whether you must restart the instance after the
parameter value is changed.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id

Request Example
---------------

.. literalinclude:: samples/datastore-version-parameter-create-request.json
   :language: javascript

Response Example
----------------

.. literalinclude:: samples/datastore-version-parameter-create-response.json
   :language: javascript




Update a datastore version configuration parameter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/mgmt/datastores/versions/{datastore_version_id}/parameters/{parameter_name}

Admin only API. Update a configuration parameter for the specified datastore
version.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id
   - parameter_name: parameter_name

Request Example
---------------

.. literalinclude:: samples/datastore-version-parameter-update-request.json
   :language: javascript

Response Example
----------------

.. literalinclude:: samples/datastore-version-parameter-update-response.json
   :language: javascript




Delete a datastore version configuration parameter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/mgmt/datastores/versions/{datastore_version_id}/parameters/{parameter_name}

Admin only API. Remove a configuration parameter for the specified datastore
version.

Normal response codes: 204

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id
   - parameter_name: parameter_name




Create datastore version
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/mgmt/datastore-versions

Admin only API. Register a datastore version, create the datastore if doesn't
exist.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id

Request Example
---------------

.. literalinclude:: samples/datastore-version-create-request.json
   :language: javascript




List datastore versions
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/mgmt/datastore-versions

Admin only API. Get all the datastore versions.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id

Response Example
----------------

.. literalinclude:: samples/datastore-version-mgmt-list-response.json
   :language: javascript




Show datastore version details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/mgmt/datastore-versions/{datastore_version_id}

Admin only API. Get information for a datastore version.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id

Response Example
----------------

.. literalinclude:: samples/datastore-version-mgmt-show-response.json
   :language: javascript




Update datastore version details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{project_id}/mgmt/datastore-versions/{datastore_version_id}

Admin only API. Update a specific datastore version.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id

Request Example
---------------

.. literalinclude:: samples/datastore-version-mgmt-patch-request.json
   :language: javascript




Delete a datastore version
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/mgmt/datastore-versions/{datastore_version_id}

Admin only API. Delete a specific datastore version.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore_version_id: datastore_version_id