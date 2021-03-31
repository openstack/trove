.. _trove-policy-file:

===========
policy.yaml
===========

.. warning::

   JSON formatted policy file is deprecated since Trove 15.0.0 (Wallaby).
   This `oslopolicy-convert-json-to-yaml`__ tool will migrate your existing
   JSON-formatted policy file to YAML in a backward-compatible way.

.. __: https://docs.openstack.org/oslo.policy/latest/cli/oslopolicy-convert-json-to-yaml.html

To see available policies, refer to :ref:`policy-configuration`.

Use the ``policy.yaml`` file to define additional access controls that will be
applied to Trove:

.. literalinclude:: ../_static/trove.policy.yaml.sample
