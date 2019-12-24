.. -*- rst -*-

=============
Instance logs
=============




List instance logs
~~~~~~~~~~~~~~~~~~

.. rest_method:: GET /v1.0/{project_id}/instances/{instanceId}/log

Listing all logs for an instance.

Different datastore backend has its own ``guest_log_exposed_logs``
configuration to determine which type of logs will be listed by default. Admin
user can get all the logs.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - logs: instance_logs
    - name: log_name
    - type: log_type
    - status: log_status
    - published: log_published_size
    - pending: log_pending_size
    - container: log_container
    - prefix: log_prefix
    - metafile: log_metafile


Response Example
----------------

.. literalinclude:: samples/instance-log-list-response.json
   :language: javascript




Show instance log details
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Show details for a instance log.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - name: log_name

Request Example
---------------

.. literalinclude:: samples/instance-log-show-request.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - log: instance_log
    - name: log_name
    - type: log_type
    - status: log_status
    - published: log_published_size
    - pending: log_pending_size
    - container: log_container
    - prefix: log_prefix
    - metafile: log_metafile

Response Example
----------------

.. literalinclude:: samples/instance-log-show-response.json
   :language: javascript




Enable instance log
~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Enable a log type for a instance.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - name: log_name
   - enable: log_enable_action

Request Example
---------------

.. literalinclude:: samples/instance-log-enable-request.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - log: instance_log
    - name: log_name
    - type: log_type
    - status: log_status
    - published: log_published_size
    - pending: log_pending_size
    - container: log_container
    - prefix: log_prefix
    - metafile: log_metafile

Response Example
----------------

.. literalinclude:: samples/instance-log-enable-response.json
   :language: javascript




Disable instance log
~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Disable a log type for a instance.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - name: log_name
   - disable: log_disable_action

Request Example
---------------

.. literalinclude:: samples/instance-log-disable-request.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - log: instance_log
    - name: log_name
    - type: log_type
    - status: log_status
    - published: log_published_size
    - pending: log_pending_size
    - container: log_container
    - prefix: log_prefix
    - metafile: log_metafile


Response Example
----------------

.. literalinclude:: samples/instance-log-disable-response.json
   :language: javascript




Publish instance log
~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Publish a log type for a instance.

Publish`` will automatically ``enable`` a log.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - name: log_name
   - publish: log_publish_action

Request Example
---------------

.. literalinclude:: samples/instance-log-publish-request.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - log: instance_log
    - name: log_name
    - type: log_type
    - status: log_status
    - published: log_published_size
    - pending: log_pending_size
    - container: log_container
    - prefix: log_prefix
    - metafile: log_metafile

Response Example
----------------

.. literalinclude:: samples/instance-log-publish-response.json
   :language: javascript




Discard instance log
~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Discard all previously published logs for a instance.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - name: log_name
   - discard: log_discard_action


Request Example
---------------

.. literalinclude:: samples/instance-log-discard-request.json
   :language: javascript


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - log: instance_log
    - name: log_name
    - type: log_type
    - status: log_status
    - published: log_published_size
    - pending: log_pending_size
    - container: log_container
    - prefix: log_prefix
    - metafile: log_metafile


Response Example
----------------

.. literalinclude:: samples/instance-log-discard-response.json
   :language: javascript