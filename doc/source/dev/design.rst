.. _design:

============
Trove Design
============

High Level description
======================

Trove is designed to support a single-tenant database within a Nova
instance. There will be no restrictions on how Nova is configured,
since Trove interacts with other OpenStack components purely through
the API.


Trove-api
=========

The trove-api service provides a RESTful API that supports JSON and
XML to provision and manage Trove instances.

* A REST-ful component
* Entry point - Trove/bin/trove-api
* Uses a WSGI launcher configured by Trove/etc/trove/api-paste.ini
* Defines the pipeline of filters; tokenauth, ratelimit, etc.
* Defines the app_factory for the troveapp as
  trove.common.api:app_factory
* The API class (a wsgi Router) wires the REST paths to the
  appropriate Controllers
* Implementation of the Controllers are under the relevant module
  (versions/instance/flavor/limits), in the service.py module
* Controllers usually redirect implementation to a class in the
  models.py module
* At this point, an api module of another component (TaskManager,
  GuestAgent, etc.) is used to send the request onwards through
  RabbitMQ


Trove-taskmanager
=================

The trove-taskmanager service does the heavy lifting as far as
provisioning instances, managing the lifecycle of instances, and
performing operations on the Database instance.

* A service that listens on a RabbitMQ topic
* Entry point - Trove/bin/trove-taskmanager
* Runs as a RpcService configured by
  Trove/etc/trove/trove-taskmanager.conf.sample which defines
  trove.taskmanager.manager.Manager as the manager - basically this is
  the entry point for requests arriving through the queue
* As described above, requests for this component are pushed to MQ
  from another component using the TaskManager's api module using
  _cast() or _call() (sync/a-sync) and putting the method's name as a
  parameter
* Trove/openstack/common/rpc/dispatcher.py- RpcDispatcher.dispatch()
  invokes the proper method in the Manager by some equivalent to
  reflection
* The Manager then redirect the handling to an object from the
  models.py module. It loads an object from the relevant class with
  the context and instance_id
* Actual handling is usually done in the models.py module


Trove-guestagent
================

The guestagent is a service that runs within the guest instance,
responsible for managing and performing operations on the Database
itself. The Guest Agent listens for RPC messages through the message
bus and performs the requested operation.

* Similar to TaskManager in the sense of running as a service that
  listens on a RabbitMQ topic
* GuestAgent runs on every DB instance, and a dedicated MQ topic is
  used (identified as the instance's id)
* Entry point - Trove/bin/trove-guestagent
* Runs as a RpcService configured by
  Trove/etc/trove/trove-guestagent.conf.sample which defines
  trove.guestagent.manager.Manager as the manager - basically this is
  the entry point for requests arriving through the queue
* As described above, requests for this component are pushed to MQ
  from another component using the GuestAgent's api module using
  _cast() or _call() (sync/a-sync) and putting the method's name as a
  parameter
* Trove/openstack/common/rpc/dispatcher.py- RpcDispatcher.dispatch()
  invokes the proper method in the Manager by some equivalent to
  reflection
* The Manager then redirect the handling to an object (usually) from
  the dbaas.py module.
* Actual handling is usually done in the dbaas.py module


Trove-conductor
===============

Conductor is a service that runs on the host, responsible for receiving
messages from guest instances to update information on the host.
For example, instance statuses and the current status of a backup.
With conductor, guest instances do not need a direct connection to the
host's database. Conductor listens for RPC messages through the message
bus and performs the relevant operation.

* Similar to guest-agent in that it is a service that listens to a
  RabbitMQ topic. The difference is conductor lives on the host, not
  the guest.
* Guest agents communicate to conductor by putting messages on the
  topic defined in cfg as conductor_queue. By default this is
  "trove-conductor".
* Entry point - Trove/bin/trove-conductor
* Runs as RpcService configured by
  Trove/etc/trove/trove-conductor.conf.sample which defines
  trove.conductor.manager.Manager as the manager. This is the entry
  point for requests arriving on the queue.
* As guestagent above, requests are pushed to MQ from another component
  using _cast() (synchronous), generally of the form
  {"method": "<method_name>", "args": {<arguments>}}
* Actual database update work is done by trove/conductor/manager.py
* The "heartbeat" method updates the status of an instance. This is
  used to report that instance has changed from NEW to BUILDING to
  ACTIVE and so on.
* The "update_backup" method changes the details of a backup, including
  its current status, size of the backup, type, and checksum.



.. Trove - Database as a Service: https://wiki.openstack.org/wiki/Trove
