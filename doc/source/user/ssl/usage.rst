Usage
=====

SSL management actions
----------------------

The following actions are available for SSL configuration.

Show current SSL status
~~~~~~~~~~~~~~~~~~~~~~~

Returns the current SSL configuration of a database instance.

The response may include:

* SSL status (on/off)
* Operating mode (basic/enforced/mtls)
* Certificate expiration date
* Certificate CN (common name)
* Certificate SAN (Subject Alternative Name)
* Certificate payload

    .. code-block:: console

        $ openstack database ssl show $dbid
        +-----------------------+----------------------------+
        | Field                 | Value                      |
        +-----------------------+----------------------------+
        | certificate_cn        | trove-test                 |
        | certificate_expire_at | 2027-02-10T09:06:25.000000 |
        | certificate_san       | IP:10.0.0.1                |
        | mode                  | basic                      |
        | status                | on                         |
        +-----------------------+----------------------------+

Enable SSL
~~~~~~~~~~

Enables SSL on the instance or rotates the existing certificate.

Requirements:

* The user must provide a reference to a PKCS12 container stored in Barbican.
* The container must include:
   * Server certificate
   * Private key for certificate
   * Optional CA chain

Example of creating a PKCS#12 container: :ref:`PKCS#12 example <ssl_pkcs12>`

Optional:

* password_ref should be provided if the container is password-protected.

Example: :ref:`Store Barbican password <store_barbican_pass>`

Parameters:

* container_ref
* password_ref (optional)

Depending on database manager, restart may be required for applying SSL
configuration.

    .. code-block:: console

        $ openstack database ssl enable $dbid https://barbican-api.example.com/9036aa7c-7c71-45e3-a9c4-a71465c4ccc9 \
          --password-ref https://barbican-api.example.com/d7211e91-4c74-43e1-8a7f-47937e56c0bd
        +------------------+-------+
        | Field            | Value |
        +------------------+-------+
        | restart_required | True  |
        +------------------+-------+

Please note that secret consumer will be created for provided certificate
container in Barbican, referencing the database instance.

Disable SSL
~~~~~~~~~~~

Disables SSL on the instance.

Depending on database manager, restart may be required for applying SSL
configuration.

    .. code-block:: console

        $ openstack database ssl disable $dbid
        +------------------+-------+
        | Field            | Value |
        +------------------+-------+
        | restart_required | True  |
        +------------------+-------+


Certificate requirements
------------------------

The provided PKCS12 container must:

* Contain a valid private key and certificate.
* Match the database instance hostname.
* Use modern cryptographic parameters.

Recommended:

* TLS 1.2 or higher.
* Proper Subject Alternative Names.
* Certificate signed by a trusted CA.


End-user recommendations
------------------------

The following guidance may help users operating production DBaaS:

* Use at least enforced encryption in production environments.
* Automate certificate rotation.
* Monitor certificate expiration.
* Use separate certificates per environment.
* Consider mTLS for sensitive workloads.
* Validate client TLS compatibility before enforcing encryption.
* Integrate SSL lifecycle with centralized secret management.

These recommendations are based on common production practices and may
vary depending on organizational security policies.
