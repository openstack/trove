# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Quotas for DB instances and resources."""

from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _
from oslo.config import cfg
from reddwarf.common import exception
from reddwarf.openstack.common import importutils
from reddwarf.quota.models import Quota
from reddwarf.quota.models import QuotaUsage
from reddwarf.quota.models import Reservation
from reddwarf.quota.models import Resource

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class DbQuotaDriver(object):
    """
    Driver to perform necessary checks to enforce quotas and obtain
    quota information.  The default driver utilizes the local
    database.
    """

    def __init__(self, resources):
        self.resources = resources

    def get_quota_by_tenant(self, tenant_id, resource):
        """Get a specific quota by tenant."""

        quotas = Quota.find_all(tenant_id=tenant_id, resource=resource).all()
        if len(quotas) == 0:
            return Quota(tenant_id, resource, self.resources[resource].default)

        return quotas[0]

    def get_all_quotas_by_tenant(self, tenant_id, resources):
        """
        Retrieve the quotas for the given tenant.

        :param resources: A list of the registered resource to get.
        :param tenant_id: The ID of the tenant to return quotas for.
        """

        all_quotas = Quota.find_all(tenant_id=tenant_id).all()
        result_quotas = dict((quota.resource, quota)
                             for quota in all_quotas
                             if quota.resource in resources)

        if len(result_quotas) != len(resources):
            for resource in resources:
                # Not in the DB, return default value
                if resource not in result_quotas:
                    quota = Quota(tenant_id,
                                  resource,
                                  self.resources[resource].default)
                    result_quotas[resource] = quota

        return result_quotas

    def get_quota_usage_by_tenant(self, tenant_id, resource):
        """Get a specific quota usage by tenant."""

        quotas = QuotaUsage.find_all(tenant_id=tenant_id,
                                     resource=resource).all()
        if len(quotas) == 0:
            return QuotaUsage.create(tenant_id=tenant_id,
                                     in_use=0,
                                     reserved=0,
                                     resource=resource)
        return quotas[0]

    def get_all_quota_usages_by_tenant(self, tenant_id, resources):
        """
        Retrieve the quota usagess for the given tenant.

        :param tenant_id: The ID of the tenant to return quotas for.
        :param resources: A list of the registered resources to get.
        """

        all_usages = QuotaUsage.find_all(tenant_id=tenant_id).all()
        result_usages = dict((usage.resource, usage)
                             for usage in all_usages
                             if usage.resource in resources)
        if len(result_usages) != len(resources):
            for resource in resources:
                # Not in the DB, return default value
                if resource not in result_usages:
                    usage = QuotaUsage.create(tenant_id=tenant_id,
                                              in_use=0,
                                              reserved=0,
                                              resource=resource)
                    result_usages[resource] = usage

        return result_usages

    def get_defaults(self, resources):
        """Given a list of resources, retrieve the default quotas.

        :param resources: A list of the registered resources.
        """

        quotas = {}
        for resource in resources.values():
            quotas[resource.name] = resource.default

        return quotas

    def reserve(self, tenant_id, resources, deltas):
        """Check quotas and reserve resources for a tenant.

        This method checks quotas against current usage,
        reserved resources and the desired deltas.

        If any of the proposed values is over the defined quota, an
        QuotaExceeded exception will be raised with the sorted list of the
        resources which are too high.  Otherwise, the method returns a
        list of reservation objects which were created.

        :param tenant_id: The ID of the tenant reserving the resources.
        :param resources: A dictionary of the registered resources.
        :param deltas: A dictionary of the proposed delta changes.
        """

        unregistered_resources = [delta for delta in deltas
                                  if delta not in resources]
        if unregistered_resources:
            raise exception.QuotaResourceUnknown(unknown=
                                                 unregistered_resources)

        quotas = self.get_all_quotas_by_tenant(tenant_id, deltas.keys())
        quota_usages = self.get_all_quota_usages_by_tenant(tenant_id,
                                                           deltas.keys())

        overs = [resource for resource in deltas
                 if (quota_usages[resource].in_use +
                     quota_usages[resource].reserved +
                     int(deltas[resource])) > quotas[resource].hard_limit]

        if overs:
            raise exception.QuotaExceeded(overs=sorted(overs))

        reservations = []
        for resource in deltas:
            reserved = deltas[resource]
            usage = quota_usages[resource]
            usage.reserved = reserved
            usage.save()

            resv = Reservation.create(usage_id=usage.id,
                                      delta=usage.reserved,
                                      status=Reservation.Statuses.RESERVED)
            reservations.append(resv)

        return reservations

    def commit(self, reservations):
        """Commit reservations.

        :param reservations: A list of the reservation UUIDs, as
                             returned by the reserve() method.
        """

        for reservation in reservations:
            usage = QuotaUsage.find_by(id=reservation.usage_id)
            usage.in_use += reservation.delta
            usage.reserved -= reservation.delta
            reservation.status = Reservation.Statuses.COMMITTED
            usage.save()
            reservation.save()

    def rollback(self, reservations):
        """Roll back reservations.

        :param reservations: A list of the reservation UUIDs, as
                             returned by the reserve() method.
        """

        for reservation in reservations:
            usage = QuotaUsage.find_by(id=reservation.usage_id)
            usage.reserved -= reservation.delta
            reservation.status = Reservation.Statuses.ROLLEDBACK
            usage.save()
            reservation.save()


class QuotaEngine(object):
    """Represent the set of recognized quotas."""

    def __init__(self, quota_driver_class=None):
        """Initialize a Quota object."""

        self._resources = {}

        if not quota_driver_class:
            quota_driver_class = CONF.quota_driver
        if isinstance(quota_driver_class, basestring):
            quota_driver_class = importutils.import_object(quota_driver_class,
                                                           self._resources)
        self._driver = quota_driver_class

    def __contains__(self, resource):
        return resource in self._resources

    def register_resource(self, resource):
        """Register a resource."""

        self._resources[resource.name] = resource

    def register_resources(self, resources):
        """Register a dictionary of resources."""

        for resource in resources:
            self.register_resource(resource)

    def get_quota_by_tenant(self, tenant_id, resource):
        """Get a specific quota by tenant."""

        return self._driver.get_quota_by_tenant(tenant_id, resource)

    def get_defaults(self):
        """Retrieve the default quotas."""

        return self._driver.get_defaults(self._resources)

    def get_all_quotas_by_tenant(self, tenant_id):
        """Retrieve the quotas for the given tenant.

        :param tenant_id: The ID of the tenant to return quotas for.
        """

        return self._driver.get_all_quotas_by_tenant(tenant_id,
                                                     self._resources)

    def reserve(self, tenant_id, **deltas):
        """Check quotas and reserve resources.

        For counting quotas--those quotas for which there is a usage
        synchronization function--this method checks quotas against
        current usage and the desired deltas.  The deltas are given as
        keyword arguments, and current usage and other reservations
        are factored into the quota check.

        This method will raise a QuotaResourceUnknown exception if a
        given resource is unknown or if it does not have a usage
        synchronization function.

        If any of the proposed values is over the defined quota, an
        QuotaExceeded exception will be raised with the sorted list of the
        resources which are too high.  Otherwise, the method returns a
        list of reservation UUIDs which were created.

        :param tenant_id: The ID of the tenant to reserve quotas for.
        """

        reservations = self._driver.reserve(tenant_id, self._resources, deltas)

        LOG.debug(_("Created reservations %(reservations)s") % locals())

        return reservations

    def commit(self, reservations):
        """Commit reservations.

        :param reservations: A list of the reservation UUIDs, as
                             returned by the reserve() method.
        """

        try:
            self._driver.commit(reservations)
        except Exception:
            LOG.exception(_("Failed to commit reservations "
                            "%(reservations)s") % locals())

    def rollback(self, reservations):
        """Roll back reservations.

        :param reservations: A list of the reservation UUIDs, as
                             returned by the reserve() method.
        """

        try:
            self._driver.rollback(reservations)
        except Exception:
            LOG.exception(_("Failed to roll back reservations "
                            "%(reservations)s") % locals())

    @property
    def resources(self):
        return sorted(self._resources.keys())


QUOTAS = QuotaEngine()

''' Define all kind of resources here '''
resources = [Resource(Resource.INSTANCES, 'max_instances_per_user'),
             Resource(Resource.VOLUMES, 'max_volumes_per_user')]

QUOTAS.register_resources(resources)
