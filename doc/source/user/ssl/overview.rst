Overview
========

Trove supports SSL/TLS to secure connections between clients and database
instances.

Users may enable, disable, and monitor SSL configuration for database
instances.

SSL operating modes
-------------------

By default, most DBMSs generate their own self-signed SSL certificate on
startup. This is referred to as the "builtin" mode and is not managed by
Trove until SSL/TLS is explicitly enabled using one of the supported
operation modes.

Basic mode
~~~~~~~~~~

* SSL is enabled on the database instance.
* Both SSL and non-SSL client connections are allowed.
* SSL encryption is optional.
* Authentication remains password-based (for example, MD5).
* No client certificate validation.

This mode provides basic protection against passive traffic interception
and may be used as intermediate step for implementing enforced or
mTLS mode in production infrastructure.

Enforced mode
~~~~~~~~~~~~~

* SSL is enabled and mandatory.
* Only encrypted connections are accepted.
* Non-SSL connections are rejected.
* Authentication remains password-based.
* No client certificate validation.

This mode improves security and helps prevent insecure client
configurations.

Mutual TLS mode (mTLS)
~~~~~~~~~~~~~~~~~~~~~~

* SSL is enabled and mandatory.
* Clients must present valid certificates. Example of :ref:`creating cert <ssl_client_cert>`
* Certificates are validated using trusted CA.
* Client identity may be based on certificate attributes.
* Password authentication is disabled.

This mode provides strong authentication and encryption.


Limitations
-----------

* SSL configuration requires the instance to be in ACTIVE state
* For replication setups, SSL is applied to all replicas