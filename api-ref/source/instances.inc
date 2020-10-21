.. -*- rst -*-

=========
Instances
=========




List database instances
~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances

Lists information for all database instances. Supported filters:
include_clustered

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id

Response Example
----------------

.. literalinclude:: samples/instance-list-response.json
   :language: javascript




List database instances(admin)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/mgmt/instances

Admin only API. Get all the instances, Could show more information such as
Cinder volume ID, Nova server information, etc.

Supported filters:

* ``deleted``.
* ``include_clustered``.
* ``project_id``: Get instances of a speficied project.

Normal response codes: 200

Response Example
----------------

.. literalinclude:: samples/instance-mgmt-list-response.json
   :language: javascript




List database instances(with details)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/detail

Lists information for all database instances with more details, such as created
and updated time, service status updated time, the failure message, etc.
Supported filters: include_clustered

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id

Response Example
----------------

.. literalinclude:: samples/instance-list-detail-response.json
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

.. literalinclude:: samples/instance-create-request.json
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
   - volume: volume
   - volume.size: volume_size
   - volume.used: volume_used
   - created: created
   - updated: updated
   - service_status_updated: service_status_updated
   - locality: locality
   - password: root_password
   - instance: instance


Response Example
----------------

.. literalinclude:: samples/instance-create-response.json
   :language: javascript




Show database instance details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}

Shows database instance details.

Lists the volume size in gigabytes (GB) and the approximate GB
used. After instance creation, the ``used`` value is greater than 0, which
is expected as databases may create some basic (non empty) files to
represent an empty schema. The response does not include the ``used``
attribute when the instance status is ``BUILD``, ``REBOOT``,
``RESIZE``, or ``ERROR``.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Parameters
-------------------

.. rest_parameters:: parameters.yaml

   - instance: instance
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
   - addresses: instance_ip_addresses
   - created: created
   - updated: updated
   - service_status_updated: service_status_updated
   - fault: instance_fault
   - fault.message: instance_fault_message
   - fault.created: instance_fault_created
   - fault.details: instance_fault_details
   - replicas: instance_replicas
   - replicas.id: instance_replica_id
   - replicas.links: instance_replica_links
   - replicas.links.href: instance_replica_link_href
   - replicas.links.rel: instance_replica_link_rel
   - replica_of: replica_of_optional
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
   - access: access
   - access.is_public: access_is_public
   - access.allowed_cidrs: access_allowed_cidrs


Response Example
----------------

.. literalinclude:: samples/instance-show-response.json
   :language: javascript




Show database instance details(admin)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/mgmt/instances/{instanceId}

Admin only API. Get an instance information, including Cinder volume, Nova
server, etc.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId


Response Example
----------------

.. literalinclude:: samples/instance-mgmt-show-response.json
   :language: javascript




Attach/Detach configuration group
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

Attach or detach a configuration group for an instance. When you pass in only
an instance ID and omit the configuration ID, this operation detaches any
configuration group that was attached to the instance.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - configuration: configuration

Request Example
---------------

.. literalinclude:: samples/instance-put-attach-config-group-request.json
   :language: javascript




Update instance name
~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

Update the instance name.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - instance: instance
   - name: instanceName

Request Example
---------------

.. literalinclude:: samples/instance-patch-update-name-request.json
   :language: javascript




Upgrade datastore version for instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

Upgrade datastore version.

During datastore version upgrading, the instance status change to ``UPGRADE``,
and changes back to ``HEALTHY`` after upgrading finishes, otherwize changes to
``ERROR`` if the upgrading fails.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - instance: instance
   - datastore_version: datastore_version

Request Example
---------------

.. literalinclude:: samples/instance-patch-upgrade-datastore-version-request.json
   :language: javascript




Detach replica
~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

Detaches a replica from its replication source.

If you created an instance that is a replica of a source instance,
you can detach the replica from the source later on. This can be useful if
the source becomes unavailable. In this case, you can detach the
replica from the source, making the replica a standalone database
instance. You can then take the new standalone instance and create
a new replica of that instance.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - instance: instance
   - replica_of: replica_of
   - slave_of: slave_of

Request Example
---------------

.. literalinclude:: samples/instance-patch-detach-replica-request.json
   :language: javascript



Update instance accessbility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  PUT /v1.0/{project_id}/instances/{instanceId}

The following operations are supported:

* If the instance should be exposed to public or not. Not providing
  ``is_public`` means private.
* The list of CIDRs that are allowed to access the database service. Not
  providing ``allowed_cidrs`` means allowing everything.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - instance: instance
   - access: access
   - access.is_public: access_is_public
   - access.allowed_cidrs: access_allowed_cidrs

Request Example
---------------

.. literalinclude:: samples/instance-update-access-request.json
   :language: javascript


Delete database instance
~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  DELETE /v1.0/{project_id}/instances/{instanceId}

Deletes a database instance.

This operation does not delete any slaves.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId




List backups of database instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/backups

Get all the backups for an instance.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Response Example
----------------

.. literalinclude:: samples/instance-backup-list-response.json
   :language: javascript




List default configuration parameters of database instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  GET /v1.0/{project_id}/instances/{instanceId}/configuration

Get the default configuration parameters for an instance.

Normal response codes: 200

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Response Example
----------------

.. literalinclude:: samples/instance-configuration-list-response.json
   :language: javascript
