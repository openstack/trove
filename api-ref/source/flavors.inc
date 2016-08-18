.. -*- rst -*-

=================
Flavors (flavors)
=================

Lists all flavors and shows details for a flavor, by ID.


Show flavor details
===================

.. rest_method::  GET /v1.0/{accountId}/flavors/{flavorId}

Shows flavor details with details of the RAM.

This resource is identical to the flavors found in the OpenStack
Compute API, but without the disk property.

The ``flavorId`` parameter must be an integer value. If you use a
floating point value for this parameter, this call truncates the
decimal portion and uses the integer portion as the ``flavorId``
value.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - flavorId: flavorId
   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-flavors-by-id-response.json
   :language: javascript














List flavors
============

.. rest_method::  GET /v1.0/{accountId}/flavors

Lists information for all available flavors.

This operation lists information for all available flavors.

This resource is identical to the flavors found in the OpenStack
Nova API, but without the disk property.


Normal response codes: 200
Error response codes:413,405,404,403,401,400,422,503,500,501,


Request
-------

.. rest_parameters:: parameters.yaml

   - accountId: accountId




Response Example
----------------

.. literalinclude:: samples/db-flavors-response.json
   :language: javascript













