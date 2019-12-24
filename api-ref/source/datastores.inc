.. -*- rst -*-

==========
Datastores
==========




List datastores
~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores

Get all the datastores registered in the system

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id

Response Example
----------------

.. literalinclude:: samples/datastore-list-response.json
   :language: javascript




Show datastore details
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/datastores/{datastore}

Shows datastore details

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - datastore: data_store

Response Example
----------------

.. literalinclude:: samples/datastore-show-response.json
   :language: javascript
