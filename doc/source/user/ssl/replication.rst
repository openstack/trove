.. _ssl_for_replication:

SSL/TLS for replication
-----------------------

Trove supports SSL/TLS configuration for replicated database clusters.
SSL configuration is managed at the primary instance level and is
automatically propagated to all replicas.

General behavior
~~~~~~~~~~~~~~~~

The following rules apply when SSL is used in replication:

* SSL can be enabled only on the primary instance.
* When SSL is enabled on the primary, the certificate and key are applied
  to all attached replicas automatically.
* All instances in the replication cluster must remain consistent with
  the primary SSL configuration.

These constraints ensure secure communication between replication nodes
and prevent configuration drift.

Prerequisites
~~~~~~~~~~~~~

Before enabling SSL in a replication cluster:

* The replication topology must be fully configured.
* All replicas must be attached to the primary instance.
* The replication cluster must be in ``ACTIVE`` and ``HEALTHY`` state.

If any instance is not ready, the operation fails. This prevents partial
SSL configuration and ensures cluster integrity.

Enable SSL in replication
~~~~~~~~~~~~~~~~~~~~~~~~~

The SSL enable operation must be performed on the primary instance only.
If the target instance is not primary, the operation is rejected.

    .. code-block:: console

        $ openstack database ssl enable <primary_id> <container_ref>

When the operation starts:

* Trove validates the state of the entire replication cluster.
* Certificates are retrieved from Barbican.
* SSL configuration is applied to the primary and all replicas.

If validation fails, no changes are applied.
Partial changes will be rolled back to the original state.

Restart behavior
~~~~~~~~~~~~~~~~

Depending on the datastore manager and database engine, a restart may be
required to apply SSL configuration.

The recommended restart order is:

1. Restart the primary instance.
2. Restart each replica sequentially.

Sequential restarts help preserve replication consistency and reduce
service disruption.

If Trove indicates that restart is required, users should avoid restarting
replicas in parallel unless supported by the specific database engine.

Replica provisioning
~~~~~~~~~~~~~~~~~~~~

When a new replica is created in an existing replication cluster:

* The replica automatically retrieves the required SSL certificate,
  private key, and trusted CA from the primary instance.
* No additional SSL configuration is required from the user.
* The replica becomes consistent with the primary SSL configuration.

This behavior ensures that all replication nodes remain securely configured
and simplifies operational workflows.

Certificate rotation
~~~~~~~~~~~~~~~~~~~~

Trove supports certificate rotation in replication clusters.

To refresh or replace a certificate:

* Call the ``ssl enable`` command on the primary instance.
* Provide a new PKCS#12 container reference and the required SSL mode.

    .. code-block:: console

        $ openstack database ssl enable <primary_id> <new_container_ref> \
            --mode <required_mode>

During this operation:

* The new certificate is retrieved from Barbican.
* The certificate and key are propagated to all replicas.
* The replication cluster remains consistent with the primary.

Depending on the datastore manager, a rolling restart of the replication
cluster may be required to apply the updated certificate.

