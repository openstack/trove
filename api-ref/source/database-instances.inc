.. -*- rst -*-

==============================
Database instances (instances)
==============================

Lists, shows details for, creates, attaches a configuration group to, detaches
a configuration group from, update the name, upgrade datastore version,
deletes, lists configuration defaults, creates root, and determines whether
root is enabled, for instances.


List database instances
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances

Lists information, including status, for all database instances.

Lists status and information for all database instances.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id


Response Example
----------------

.. literalinclude:: samples/db-instances-index-response.json
   :language: javascript




Show database instance details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}

Shows database instance details.

Lists the status and details of the database instance.

Lists the volume size in gigabytes (GB) and the approximate GB
used. After instance creation, the ``used`` value is greater than 0, which
is expected as databases may create some basic (non empty) files to
represent an empty schema. The response does not include the ``used``
attribute when the instance status is ``BUILD``, ``REBOOT``,
``RESIZE``, or ``ERROR``.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id


Response Example
----------------

.. literalinclude:: samples/db-instance-status-detail-response.json
   :language: javascript




Create database instance
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances

Creates a database instance.

Asynchronously provisions a database instance. You must specify a flavor ID, a
volume size and the tenant network ID. The service provisions the instance with
a volume of the requested size, which serves as storage for the database
instance. The database service can only be access within the tenant network,
unless the ``access`` parameter is defined.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

    - project_id: project_id
    - users: users
    - users.name: user_name1
    - users.password: user_password
    - users.host: user_host
    - users.databases: user_databases
    - users.databases.name: user_database_name
    - datastore: datastore1
    - datastore.type: datastore_type
    - datastore.version: datastore_version
    - name: instanceName1
    - flavorRef: flavorRef
    - volume: volume
    - volume.size: volume_size
    - volume.type: volume_type
    - modules: modules
    - modules.id: module_id
    - restorePoint: restore_point
    - restorePoint.backupRef: restore_point_backupref
    - availability_zone: availability_zone
    - nics: nics
    - replica_of: replica_of
    - replica_count: replica_count
    - locality: locality
    - region_name: region_name
    - databases: databases
    - databases.characterSet: characterSet
    - databases.collate: collate
    - instance: instance
    - configuration: configuration
    - access: access
    - access.is_public: access_is_public
    - access.allowed_cidrs: access_allowed_cidrs


Request Example
---------------

.. literalinclude:: samples/db-create-instance-request.json
   :language: javascript


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - id: instanceId1
   - name: instanceName1
   - status: instance_status
   - links: instance_links
   - links.href: instance_link_href
   - links.rel: instance_link_rel
   - flavor: flavor
   - flavor.id: flavorId1
   - flavor.links: flavor_links
   - flavor.links.href: flavor_link_href
   - flavor.links.rel: flavor_link_rel
   - datastore: datastore2
   - datastore.type: datastore_type
   - datastore.version: datastore_version1
   - region: region_name2
   - tenant_id: tenant_id
   - volume: volume
   - volume.size: volume_size
   - volume.used: volume_used
   - hostname: instance_hostname
   - ip: instance_ip_address
   - created: created
   - updated: updated
   - fault: instance_fault
   - fault.message: instance_fault_message
   - fault.created: instance_fault_created
   - fault.details: instance_fault_details
   - replicas: instance_replicas
   - replicas.id: instance_replica_id
   - replicas.links: instance_replica_links
   - replicas.links.href: instance_replica_link_href
   - replicas.links.rel: instance_replica_link_rel
   - configuration: configuration1
   - configuration.id: configuration_id
   - configuration.name: configuration_name
   - configuration.links: configuration_links
   - configuration.links.href: configuration_link_href
   - configuration.links.rel: configuration_link_rel
   - locality: locality
   - local_storage_used: local_storage_used
   - password: root_password
   - cluster_id: cluster_id
   - shard_id: shard_id
   - server_id: server_id
   - volume_id: volume_id
   - encrypted_rpc_messaging: encrypted_rpc_messaging
   - instance: instance


Response Example
----------------

.. literalinclude:: samples/db-create-instance-response.json
   :language: javascript




Attach configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

Attaches a configuration group to an instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - configuration: configuration
   - instanceId: instanceId
   - project_id: project_id


Request Example
---------------

.. literalinclude:: samples/db-attach-config-group-request.json
   :language: javascript




Detach configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

Detaches a configuration group from an instance.

When you pass in only an instance ID and omit the configuration ID,
this operation detaches any configuration group that was attached
to the instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - configuration: configuration
   - instanceId: instanceId
   - project_id: project_id

Request Example
---------------

.. literalinclude:: samples/db-detach-config-group-request.json
   :language: javascript




Detach replica
~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{project_id}/instances/{instanceId}

Detaches a replica from its replication source.

If you created an instance that is a replica of a source instance,
you can detach the replica from the source. This can be useful if
the source becomes unavailable. In this case, you can detach the
replica from the source, making the replica a standalone database
instance. You can then take the new standalone instance and create
a new replica of that instance.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - replica_of: replica_of
   - slave_of: slave_of
   - instanceId: instanceId
   - project_id: project_id


Request Example
---------------

.. literalinclude:: samples/db-detach-replica-request.json
   :language: javascript




Update instance name
~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{project_id}/instances/{instanceId}

Update the instance name.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instance: instance
   - name: instanceName
   - instanceId: instanceId
   - project_id: project_id


Request Example
---------------

.. literalinclude:: samples/db-update-instance-name-request.json
   :language: javascript




Upgrade datastore version
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PATCH /v1.0/{project_id}/instances/{instanceId}

Upgrade datastore version.

During datastore version upgrading, the instance status change to ``UPGRADE``,
and changes back to ``HEALTHY`` after upgrading finishes, otherwize changes to
``ERROR`` if the upgrading fails.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), badMediaType(415),
unprocessableEntity(422), instanceFault(500), notImplemented(501),
serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instance: instance
   - datastore_version: datastore_version
   - instanceId: instanceId
   - project_id: project_id


Request Example
---------------

.. literalinclude:: samples/db-upgrade-instance-datastore-version-request.json
   :language: javascript




Delete database instance
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/instances/{instanceId}

Deletes a database instance, including any associated data.

This operation does not delete any read slaves.

You cannot complete this operation when the instance state is
either ``REBUILDING`` or ``BUILDING``.

Normal response codes: 202

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id




List configuration defaults
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/configuration

Lists the configuration defaults for an instance.

Normal response codes: 200

Error response codes: badRequest(400), unauthorized(401), forbidden(403),
itemNotFound(404), badMethod(405), overLimit(413), unprocessableEntity(422),
instanceFault(500), notImplemented(501), serviceUnavailable(503)


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - project_id: project_id


Response Example
----------------

.. literalinclude:: samples/db-list-cfg-defaults-response.json
   :language: javascript
