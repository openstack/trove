Generate Trove policies sample
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trove policies sample are no longer provided, instead it could be generated
by running the following command from the top of the trove directory:

    tox -egenpolicy


Use customized policy file
~~~~~~~~~~~~~~~~~~~~~~~~~~

As Trove uses policy in code now, it's not necessary to add a policy file for
Trove components to run. But when a customized policy is needed, Trove will
take ``/etc/trove/policy.json`` by default. The location of the policy file
can also be overriden by adding following lines in Trove config file:

    [oslo_policy]
    policy_file = /path/to/policy/file
