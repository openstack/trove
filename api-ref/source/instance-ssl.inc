.. -*- rst -*-

=============
Instance SSL
=============




Show instance SSL status
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method:: GET /v1.0/{project_id}/instances/{instanceId}/ssl

Show current SSL status for the instance and information about current
SSL certificate (if present).

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - include_certificate: ssl_include_cert


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - ssl: instance_ssl
    - ssl.status: ssl_status
    - ssl.mode: ssl_mode
    - ssl.certificate: ssl_certificate
    - ssl.certificate.payload: ssl_certificate_payload
    - ssl.certificate.cn: ssl_certificate_cn
    - ssl.certificate.expire_at: ssl_certificate_expire_at
    - ssl.certificate.san: ssl_certificate_san


Response Example
----------------

.. literalinclude:: samples/instance-ssl-show-response.json
   :language: javascript




SSL enable action for instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/ssl

Enable SSL for a database instance, or renew an existing SSL
certificate on the instance.

Instance should be in `ACTIVE/HEALTHY` state.

Barbican consumer will be added for `container_ref` secret.

For replication, the SSL action should be called against the primary node only.
The configuration will be applied sequentially to each replica in a transactional manner.
If an error occurs on a single node, the entire configuration will be rolled back.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - ssl: instance_ssl
   - ssl.enable: ssl_action_enable
   - ssl.container_ref: ssl_container_ref
   - ssl.password_ref: ssl_password_ref

Request Example
---------------

.. literalinclude:: samples/instance-ssl-action-request.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - ssl: instance_ssl
    - ssl.status: ssl_status
    - ssl.container_ref: ssl_container_ref
    - ssl.restart_required: ssl_restart_required

Response Example
----------------

.. literalinclude:: samples/instance-ssl-action-response.json
   :language: javascript



SSL disable action for instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/ssl

Disable SSL for a database instance.

Note that disabling SSL for some datastores, e.g. for MySQL 8.4 and
above, is not supported.

Barbican consumer will be removed from `container_ref` secret.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - ssl: instance_ssl
   - ssl.disable: ssl_action_disable

Request Example
---------------

.. literalinclude:: samples/instance-ssl-action-request-disable.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - ssl: instance_ssl
    - ssl.status: ssl_status
    - ssl.restart_required: ssl_restart_required

Response Example
----------------

.. literalinclude:: samples/instance-ssl-action-response-disable.json
   :language: javascript



SSL rollback action for instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method:: POST /v1.0/{project_id}/instances/{instanceId}/ssl

Roll back the last SSL configuration on the instance.

Use only in emergencies. Note that the Barbican consumer state may be
inconsistent after this operation because the guest agent applies the stored
certificate payload directly, without referring to the Barbican secret.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - ssl: instance_ssl
   - ssl.rollback: ssl_action_rollback

Request Example
---------------

.. literalinclude:: samples/instance-ssl-action-request-rollback.json
   :language: javascript

Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

    - ssl: instance_ssl
    - ssl.status: ssl_status
    - ssl.restart_required: ssl_restart_required

Response Example
----------------

.. literalinclude:: samples/instance-ssl-action-response-rollback.json
   :language: javascript
