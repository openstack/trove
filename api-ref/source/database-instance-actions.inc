.. -*- rst -*-

==================================
Database instance actions (action)
==================================

Resizes instances and volumes and restarts instances.


Restart instance
================

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/action

Restarts the database service for an instance.

The restart operation restarts only the MySQL instance. Restarting
MySQL erases any dynamic configuration settings that you make in
MySQL.

The MySQL service is unavailable until the instance restarts.

If the operation succeeds, it returns the ``Accepted (202)``
response code.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-instance-restart-request.json
   :language: javascript


















Resize instance
===============

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/action

Resizes the memory for an instance.

If you provide a valid ``flavorRef``, this operation changes the
memory size of the instance, and restarts MySQL.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-instance-resize-instance-request.json
   :language: javascript


















Resize instance volume
======================

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/action

Resizes the volume that is attached to an instance.

You can use this operation to increase but not decrease the volume
size. A valid volume size is an integer value in gigabytes (GB).

You cannot increase the volume to a size that is larger than the
API volume size limit.

If this operation succeeds, it returns a 202 Accepted response.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-instance-resize-volume-request.json
   :language: javascript


















Promote instance to replica source
==================================

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/action

Promotes a replica.

If you have set up replication, and the base instance is still
reachable, you can use this operation to promote a replica to be
the new base instance.

This can be useful if you want to make a configuration change to
the base instance that your replicas are replicating from. For
example, you might want to increase the disk or CPU capacity. If
you made the change on the base instance directly, you would need
to take the base instance down for the duration of the operation.
Instead, you can create a replica, make the configuration change on
the replica, and then promote the replica to become the new base
instance.

For ``instanceId``, pass in the instance ID of the replica you want
to promote.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-instance-promote-replica-request.json
   :language: javascript


















Delete replication base instance
================================

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/action

Deletes the base instance in a replication set.

If the base instance becomes unreachable, you can use this
operation to delete the base instance.

This operation:

- Finds the replica that has processed the greatest number of
  transactions and picks that replica to use as the new base
  instance.

- Transfers the public IP of the old base instance to the new base
  instance (which is the newly-promoted replica).

- Deletes the old base instance.

- Takes all the instances in the replication set and makes them
  start replicating from the new base instance.

For ``instanceId``, pass in the instance ID of the unreachable base
instance.

Error response codes:202,413,415,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-instance-eject-replica-request.json
   :language: javascript

















