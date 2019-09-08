.. -*- rst -*-

======================
Database instance logs
======================

List, show details, enable, disable, publish, and discard logs for instances.


List instance logs
~~~~~~~~~~~~~~~~~~

.. rest_method:: GET /v1.0/{project_id}/instances/{instanceId}/log

Listing all logs for an instance.

Different datastore backend has its own ``guest_log_exposed_logs``
configuration to determine which type of logs will be listed by default. For
admin context, all logs will be listed.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id


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

.. literalinclude:: samples/db-instance-list-logs-response.json
   :language: javascript




Show instance log details
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Show details for a instance log.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id
   - name: log_name


Request Example
---------------

.. literalinclude:: samples/db-instance-show-log-request.json
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

.. literalinclude:: samples/db-instance-show-log-response.json
   :language: javascript




Enable instance log
~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Enable a log type for a instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id
   - name: log_name
   - enable: log_enable_action


Request Example
---------------

.. literalinclude:: samples/db-instance-enable-log-request.json
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

.. literalinclude:: samples/db-instance-enable-log-response.json
   :language: javascript




Disable instance log
~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Disable a log type for a instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id
   - name: log_name
   - disable: log_disable_action


Request Example
---------------

.. literalinclude:: samples/db-instance-disable-log-request.json
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

.. literalinclude:: samples/db-instance-disable-log-response.json
   :language: javascript




Publish instance log
~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Publish a log type for a instance.

*Note:* ``publish`` will automatically ``enable`` a log.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id
   - name: log_name
   - publish: log_publish_action


Request Example
---------------

.. literalinclude:: samples/db-instance-publish-log-request.json
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

.. literalinclude:: samples/db-instance-publish-log-response.json
   :language: javascript




Discard instance log
~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/log

Discard all previously published logs for a instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id
   - name: log_name
   - discard: log_discard_action


Request Example
---------------

.. literalinclude:: samples/db-instance-discard-log-request.json
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

.. literalinclude:: samples/db-instance-discard-log-response.json
   :language: javascript
