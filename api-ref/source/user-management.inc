.. -*- rst -*-

=============
Users (users)
=============

Creates, lists all, and deletes users.


Enable root user
================

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/root

Enables the root user for a database instance and returns the root password.

This operation generates a root password for the root user and
enables the root user to log in from any host.

Changes that you make as a root user can impact the database
instance and API operations in unpredictable and detrimental ways.
When you enable the root user, you accept the possibility that we
cannot support your database instance. We might not be able to
assist you if you change core MySQL settings. These changes can be,
but are not limited to, turning off bin logs, removing users that
we use to access your instance, and so on.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-enable-root-user-response.json
   :language: javascript














Show root-enabled status for database instance
==============================================

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}/root

Shows root-enabled status for a database instance.

Returns ``true`` if root user is enabled for a database instance.
Otherwise, returns ``false``.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-check-root-user-response.json
   :language: javascript














Disable root user
=================

.. rest_method::  DELETE /v1.0/{accountId}/instances/{instanceId}/root

Disables the root user.

Error response codes:202,413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId
















Delete user
===========

.. rest_method::  DELETE /v1.0/{accountId}/instances/{instanceId}/users/{name}

Deletes a user for a database instance.

Do not use periods in user names. A bug in a Python library that
Rackspace uses that can cause incorrect user deletions to occur if
you use a period (.) in the user name. In this case, the bug in the
library truncates the user name to the portion from the beginning
up to the period. For example, for the ``my.userA`` user, the bug
truncates the user name to ``my``, and if the ``user`` exists, that
user is incorrectly deleted.

Error response codes:202,413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId
















Create user
===========

.. rest_method::  POST /v1.0/{accountId}/instances/{instanceId}/users

Creates a user for a database instance.

Asynchronously provisions a new user for the database instance by
using the configuration that you define in the request object.
After the API validates the request and starts progress on the
provisioning process, the call returns the ``Accepted (202)``
response code.

If the API cannot fulfill the corresponding request due to
insufficient data or data that is not valid, the API returns the
``Bad Request (400)`` response code with information about the
nature of the failure. You cannot recover from validation errors.
You must correct the cause of the failure and the request again.

This table lists the required attributes for creating users:

**Required attributes for user**

+-----------------+---------------------------------------------------------------------+------------------------------------+----------+
|    Applies to   |                                 Name                                |            Description             | Required |
+-----------------+---------------------------------------------------------------------+------------------------------------+----------+
|       User      |                                 name                                | Name of the user for the database. |   Yes    |
+-----------------+---------------------------------------------------------------------+------------------------------------+----------+
|     password    |                  User password for database access.                 |                Yes                 |          |
+-----------------+---------------------------------------------------------------------+------------------------------------+----------+
| (database) name | Name of the database that the user can access. You must specify one |                 No                 |          |
|                 |                       or more database names.                       |                                    |          |
+-----------------+---------------------------------------------------------------------+------------------------------------+----------+

 **Notes**

- The operation grants the user all privileges on the databases.

- Do not use the ``root`` user name, which is reserved.

These tables list the valid characters for database names, user
names, and passwords.

**Valid characters in database name, user name, and password**

+---------------------------------------------------------------------------------------------------------------------------------+
|                                                            Character                                                            |
+---------------------------------------------------------------------------------------------------------------------------------+
|                                             Letters (upper and lower cases allowed)                                             |
+---------------------------------------------------------------------------------------------------------------------------------+
|                                                             Numbers                                                             |
+---------------------------------------------------------------------------------------------------------------------------------+
| ``@``, ``?``, ``#``, and spaces are allowed, but **not** at the beginning and end of the database name, user name, and password |
+---------------------------------------------------------------------------------------------------------------------------------+
|                             ``_`` is allowed anywhere in the database name, user name, and password                             |
+---------------------------------------------------------------------------------------------------------------------------------+

**Characters that are not allowed in database name, user name, and password**

+---------------------------------------------------------+
|                        Character                        |
+---------------------------------------------------------+
|                      Single quotes                      |
+---------------------------------------------------------+
|                      Double quotes                      |
+---------------------------------------------------------+
|                       Back quotes                       |
+---------------------------------------------------------+
|                        Semicolons                       |
+---------------------------------------------------------+
|                          Commas                         |
+---------------------------------------------------------+
|                       Back slashes                      |
+---------------------------------------------------------+
|                     Forward slashes                     |
+---------------------------------------------------------+
| Spaces at the front or end of the user name or password |
+---------------------------------------------------------+

**Length restrictions for database name, user name, and password**

+------------------------------+-----------------------------+
|         Restriction          |            Value            |
+------------------------------+-----------------------------+
| Database name maximum length |              64             |
+------------------------------+-----------------------------+
|   User name maximum length   |              16             |
+------------------------------+-----------------------------+
|   Password maximum length    | unlimited (no restrictions) |
+------------------------------+-----------------------------+

Error response codes:202,413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId

Request Example
---------------

.. literalinclude:: samples/db-create-users-request.json
   :language: javascript

















List database instance users
============================

.. rest_method::  GET /v1.0/{accountId}/instances/{instanceId}/users

Lists the users in a database instance and the associated databases for that user.

This operation does not return system users. A system user is a
database administrator who administers the health of the database.
Also, this operation returns the ``root`` user only if it is
enabled.

The following notes apply to MySQL users:

- User names can be up to 16 characters long.

- When you create accounts with INSERT, you must use FLUSH
  PRIVILEGES to tell the server to reload the grant tables.

- For additional information, See:
  `http://dev.mysql.com/doc/refman/5.1/en/user-account-
  management.html <http://dev.mysql.com/doc/refman/5.1/en/user-
  account-management.html>`_


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - instanceId: instanceId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-list-users-response.json
   :language: javascript













