.. -*- rst -*-

======
Quotas
======

Show and update quotas.

Show resources quota for a specific project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/mgmt/quotas/{user_project}

Admin only action by default.

Normal response codes: 200


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - user_project: user_project

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - quotas: quota_list
    - resource: quota_resource
    - in_use: quota_in_use
    - limit: quota_limit
    - reserved: quota_reserved

Response Example
----------------

.. literalinclude:: samples/quota-show-response.json
   :language: javascript


Update resources quota for a specific project
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/mgmt/quotas/{user_project}

Admin only action by default.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - user_project: user_project
   - quotas: quotas

Request Example
---------------

.. literalinclude:: samples/quota-update.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - quotas: quotas

Response Example
----------------

.. literalinclude:: samples/quota-update.json
   :language: javascript
