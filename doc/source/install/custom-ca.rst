Configure a Self-Signed CA
==========================

If the OpenStack cloud uses services secured with a self-signed certificate
or a certificate signed by a private Certificate Authority (CA), Trove
guest instances must be able to verify that certificate.

There are at least two known ways to configure a custom CA for Trove guest
instances:

* Add the CA certificate to the guest operating system's trusted CA store.
* Inject the CA certificate into the guest and configure Trove to use it explicitly.

The second approach does not modify the guest operating system's global
CA trust store and can be useful when the CA is required only by Trove services.

Cloudinit files which Trove is injecting into the guest instance are located
in the `/etc/trove/cloudinit/` directory.


Add the CA to the Guest Operating System
----------------------------------------

The CA certificate can be added to the guest operating system's trusted
CA store using the ``ca-certs`` section of cloud-init.

For example:

.. code-block:: yaml

   #cloud-config
   ca_certs:
     trusted:
        - |
         -----BEGIN CERTIFICATE-----
         YOUR-ORGS-TRUSTED-CA-CERT-HERE
         -----END CERTIFICATE-----
        - |
         -----BEGIN CERTIFICATE-----
         YOUR-ORGS-TRUSTED-CA-CERT-HERE
         -----END CERTIFICATE-----

This makes the CA available to applications that use the operating system's
trusted certificate store.

For more information, see the `cloud-init documentation <https://cloudinit.readthedocs.io/en/17.2/topics/examples.html#configure-an-instances-trusted-ca-certificates>`_.


Inject the CA and Configure Trove to Use It
-------------------------------------------

Alternatively, the CA certificate can be injected into the guest instance
as a file and configured explicitly in the Trove configuration.

For example, if the CA is used to verify the certificate of a service such
as RabbitMQ, configure the corresponding Trove service with:

.. code-block:: ini

   ssl_ca_file = /etc/trove/rabbitmq_ca.crt

Then inject the CA certificate into the guest using cloud-init:

.. code-block:: yaml

   #cloud-config
   write_files:
   - path: /etc/trove/rabbitmq_ca.crt
     permissions: '0644'
     owner: root:root
     content: |
       -----BEGIN CERTIFICATE-----
       YOUR-ORGS-TRUSTED-CA-CERT-HERE
       -----END CERTIFICATE-----

In this configuration, the CA certificate is available at
`/etc/trove/rabbitmq_ca.crt` but is not added to the guest operating system's
global trusted CA store. Only the Trove component configured with
`ssl_ca_file` uses this certificate for TLS verification.

The certificate content must be the PEM-encoded CA certificate, including the
`-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----` delimiters.
