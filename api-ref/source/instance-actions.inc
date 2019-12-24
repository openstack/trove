.. -*- rst -*-

================
Instance actions
================




Restart instance
~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/action

Restarts the database service for an instance.

The restart operation restarts only the database instance. Restarting
the database erases any dynamic configuration settings that you make
in the database instance.

The database service is unavailable until the instance restart finishes.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-action-restart-request.json
   :language: javascript




Resize instance flavor
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/action

Resizes the (Nova)flavor for an instance.

If you provide a valid ``flavorRef``, this operation changes the
memory size of the instance, and restarts the database.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - flavorRef: flavorRef

Request Example
---------------

.. literalinclude:: samples/instance-action-resize-request.json
   :language: javascript




Resize instance volume
~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/action

Resizes the volume that is attached to an instance.

You can use this operation to increase but not decrease the volume
size. A valid volume size is an integer value in gigabytes (GB).

You cannot increase the volume to a size that is larger than the
API volume size limit.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId
   - volume: volume

Request Example
---------------

.. literalinclude:: samples/instance-action-resize-volume-request.json
   :language: javascript




Promote instance to replica master
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/action

Promotes a replica.

If you have set up replication, and the master instance is still reachable, you
can use this operation to promote a replica to be the new master instance.

This can be useful if you want to make a configuration change or maintenance to
the master instance. If you made the change on the master instance directly,
you would need to take the master instance down for the duration of the
operation. Instead, you can create a replica, make the configuration change on
the replica, and then promote the replica to become the new master instance.

Once this command is executed, the status of all the instances will be set to
``PROMOTE`` and Trove will work its magic until all of them to come back to
``HEALTHY``.

The ``instanceId`` is the instance ID of the replica you want to promote.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-action-promote-replica-request.json
   :language: javascript




Eject the master instance
~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/action

Remove the master instance in a replication set.

This should be only done in a failed master scenario. This command ejects the
current master and then forces a re-election for the new master. The new master
is effectively the one with the most current replica of the old master.

Once this command is executed, the status of all the instances will be set to
``EJECT`` and Trove will work its magic until all of them to come back to
``HEALTHY``.

The ``instanceId`` is the ID of the current unavailable master instance.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-action-eject-replica-request.json
   :language: javascript




Reset instance status
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/instances/{instanceId}/action

Set instance service status to ``ERROR`` and clear the current task status.
Mark any running backup operations as ``FAILED``.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-action-reset-status-request.json
   :language: javascript




Stop database service
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/mgmt/instances/{instanceId}/action

Admin only API. Stop database service inside an instance.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-mgmt-action-stop-request.json
   :language: javascript




Reboot instance
~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/mgmt/instances/{instanceId}/action

Admin only API. Reboot the database instance, database service will be stopped
before rebooting.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-mgmt-action-reboot-request.json
   :language: javascript




Cold Migrate instance
~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/mgmt/instances/{instanceId}/action

Admin only API. Migrate(resize) the database instance, database service will be
stopped before migrating.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-mgmt-action-migrate-request.json
   :language: javascript




Reset instance task status
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. rest_method::  POST /v1.0/{project_id}/mgmt/instances/{instanceId}/action

Admin only API. Reset task status of an instance, mark any running backup
operations as ``FAILED``.

Normal response codes: 202

Request
-------

.. rest_parameters:: parameters.yaml

   - project_id: project_id
   - instanceId: instanceId

Request Example
---------------

.. literalinclude:: samples/instance-mgmt-action-reset-task-status-request.json
   :language: javascript