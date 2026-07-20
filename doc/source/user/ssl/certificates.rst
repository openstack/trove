.. _ssl_pkcs12:

Preparing Certificates
======================

This section describes how to generate and prepare certificates for use
with Trove.

Generate CA private key
~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

       $ openssl genrsa -out ca.key 2048
       Generating RSA private key, 2048 bit long modulus
       ........................................+++++
       ................................+++++
       e is 65537 (0x10001)

.. warning::

   Keep the CA private key in a secure offline location.

Create self-signed CA certificate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

       $ openssl req -x509 -new -nodes \
           -key ca.key \
           -sha256 \
           -days 365 \
           -subj "/CN=Trove Test CA" \
           -out ca-cert.crt

Generate server private key
~~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

       $ openssl genrsa -out server.key 2048
       Generating RSA private key, 2048 bit long modulus
       ........................................+++++
       ........................+++++
       e is 65537 (0x10001)

Generate server CSR
~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

       $ openssl req -new \
           -key server.key \
           -out server.csr \
           -subj "/CN=db.example.com" \
           -addext "subjectAltName=DNS:db.example.com,DNS:db.internal,IP:10.0.0.10"

.. note::

    Please note that domain name and (or) IP address must match the real
    IP address that your client will use for connection to DB server.

Sign server certificate with CA
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openssl x509 -req \
            -in server.csr \
            -CA ca-cert.crt \
            -CAkey ca.key \
            -CAcreateserial \
            -out server.crt \
            -days 365 \
            -sha256
        Signature ok
        subject=/CN=db.example.com
        Getting CA Private Key

Create PKCS#12 container
~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openssl pkcs12 -export \
            -inkey server.key \
            -in server.crt \
            -certfile ca-cert.crt \
            -passout pass:MySecretPassword01! \
            -out server.p12

.. _store_barbican_pass:

Store PKCS#12 password in Barbican
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openstack secret store --name my-password-for-pkcs12 \
            --payload MySecretPassword01!
        +---------------+----------------------------------------------------------------------------------+
        | Field         | Value                                                                            |
        +---------------+----------------------------------------------------------------------------------+
        | Secret href   | https://barbican-api.example.com/v1/secrets/f54bc745-00e7-4e42-bd6a-0e80879b62f6 |
        | Name          | my-password-for-pkcs12                                                           |
        | Created       | None                                                                             |
        | Status        | None                                                                             |
        | Content types | None                                                                             |
        | Algorithm     | aes                                                                              |
        | Bit length    | 256                                                                              |
        | Secret type   | opaque                                                                           |
        | Mode          | cbc                                                                              |
        | Expiration    | None                                                                             |
        +---------------+----------------------------------------------------------------------------------+

Upload PKCS#12 to Barbican
~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openstack secret store --file server.p12 \
            --name my-pkcs12-container-for-ssl \
            --secret-type certificate
        +---------------+----------------------------------------------------------------------------------+
        | Field         | Value                                                                            |
        +---------------+----------------------------------------------------------------------------------+
        | Secret href   | https://barbican-api.example.com/v1/secrets/c3fd1238-7d85-4eec-8e36-53c4953bab39 |
        | Name          | my-pkcs12-container-for-ssl                                                      |
        | Created       | None                                                                             |
        | Status        | None                                                                             |
        | Content types | None                                                                             |
        | Algorithm     | aes                                                                              |
        | Bit length    | 256                                                                              |
        | Secret type   | certificate                                                                      |
        | Mode          | cbc                                                                              |
        | Expiration    | None                                                                             |
        +---------------+----------------------------------------------------------------------------------+

.. _ssl_client_cert:

Create client certificate for mTLS authentication
-------------------------------------------------

Generate client private key
~~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openssl genrsa -out client.key 2048

Generate client CSR
~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openssl req -new \
            -key client.key \
            -out client.csr \
            -subj "/CN=dbuser"

.. note::

    Please note that subject should be equal to a real user name used
    to connect to the database.

Sign client certificate
~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        $ openssl x509 -req \
           -in client.csr \
           -CA ca-cert.crt \
           -CAkey ca.key \
           -CAcreateserial \
           -out client.crt \
           -days 365 \
           -sha256

PostgreSQL connection using client certificate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    .. code-block:: console

        psql "sslmode=verify-full \
              sslrootcert=ca-cert.crt \
              sslcert=client.crt \
              sslkey=client.key \
              host=10.0.0.10 user=dbuser dbname=test_db"