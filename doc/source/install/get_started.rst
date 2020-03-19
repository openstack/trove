=========================
Database service overview
=========================

The Database service provides scalable and reliable cloud provisioning
functionality for both relational and non-relational database engines.
Users can quickly and easily use database features without the burden of
handling complex administrative tasks. Cloud users and database
administrators can provision and manage multiple database instances as
needed.

The Database service provides resource isolation at high performance
levels, and automates complex administrative tasks such as deployment,
configuration, patching, backups, restores, and monitoring.

**Process flow example**

This example is a high-level process flow for using Database services:

#. The OpenStack Administrator configures the basic infrastructure using
   the following steps:

   #. Install the Database service.
   #. Create an image for each type of database. For example, one for MySQL
      and one for MongoDB.
   #. Use the :command:`trove-manage` command to import images and offer them
      to tenants.

#. The OpenStack end user deploys the Database service using the following
   steps:

   #. Create a Database service instance using the
      ``openstack database instance create`` command.
   #. Use the :command:`openstack database instance list` command to get the ID
      of the instance, followed by the
      :command:`openstack database instance show` command to get the IP address
      of it.
   #. Access the Database service instance using typical database access
      commands. For example, with MySQL:

      .. code-block:: console

         $ mysql -u myuser -p -h TROVE_IP_ADDRESS mydb

**Components**

The Database service includes the following components:

``python-troveclient`` command-line client
  A CLI that communicates with the ``trove-api`` component.

``trove-api`` component
  This component is responsible for providing the RESTful API. It talks to the
  task manager for complex tasks, but it can also talk to the guest agent
  directly to perform simple tasks, such as retrieving databases or users from
  trove instance.

``trove-conductor`` service
  The conductor component is responsible for updating the Trove backend
  database with the information that the guest agent sends regarding the
  instances. It eliminates the need for direct database access by all the guest
  agents for updating information.

``trove-taskmanager`` service
  The task manager is the engine responsible for doing the majority of the
  work. It is responsible for provisioning instances, managing the life cycle,
  and performing different operations. The task manager normally sends common
  commands to trove guest agent, which are of an abstract nature; it is the
  responsibility of the guest agent to read them and issue database-specific
  commands in order to execute them.

``trove-guestagent`` service
  The guest agent runs inside the Nova instances that are used to run the
  database engines. The agent listens to the messaging bus for the topic and is
  responsible for actually translating and executing the commands that are sent
  to it by the task manager component for the particular datastore.
