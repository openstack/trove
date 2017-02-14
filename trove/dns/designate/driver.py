# Copyright (c) 2013 OpenStack Foundation
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

"""
Dns Driver that uses Designate DNSaaS.
"""

import base64
import hashlib

from designateclient.v1 import Client
from designateclient.v1.records import Record
from oslo_log import log as logging
from oslo_utils import encodeutils
import six

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.dns import driver


CONF = cfg.CONF

DNS_TENANT_ID = CONF.dns_account_id
DNS_AUTH_URL = CONF.dns_auth_url
DNS_ENDPOINT_URL = CONF.dns_endpoint_url
DNS_SERVICE_TYPE = CONF.dns_service_type
DNS_REGION = CONF.dns_region
DNS_USERNAME = CONF.dns_username
DNS_PASSKEY = CONF.dns_passkey
DNS_TTL = CONF.dns_ttl
DNS_DOMAIN_ID = CONF.dns_domain_id
DNS_DOMAIN_NAME = CONF.dns_domain_name


LOG = logging.getLogger(__name__)


class DesignateObjectConverter(object):

    def domain_to_zone(self, domain):
        return DesignateDnsZone(id=domain.id, name=domain.name)

    def record_to_entry(self, record, dns_zone):
        return driver.DnsEntry(name=record.name, content=record.data,
                               type=record.type, ttl=record.ttl,
                               priority=record.priority, dns_zone=dns_zone)


def create_designate_client():
    """Creates a Designate DNSaaS client."""
    client = Client(auth_url=DNS_AUTH_URL,
                    username=DNS_USERNAME,
                    password=DNS_PASSKEY,
                    tenant_id=DNS_TENANT_ID,
                    endpoint=DNS_ENDPOINT_URL,
                    service_type=DNS_SERVICE_TYPE,
                    region_name=DNS_REGION)
    return client


class DesignateDriver(driver.DnsDriver):

    def __init__(self):
        self.dns_client = create_designate_client()
        self.converter = DesignateObjectConverter()
        self.default_dns_zone = DesignateDnsZone(id=DNS_DOMAIN_ID,
                                                 name=DNS_DOMAIN_NAME)

    def create_entry(self, entry, content):
        """Creates the entry in the driver at the given dns zone."""
        dns_zone = entry.dns_zone or self.default_dns_zone
        if not dns_zone.id:
            raise TypeError(_("The entry's dns_zone must have an ID "
                              "specified."))
        name = entry.name
        LOG.debug("Creating DNS entry %s.", name)
        client = self.dns_client
        # Record name has to end with a '.' by dns standard
        record = Record(name=entry.name + '.',
                        type=entry.type,
                        data=content,
                        ttl=entry.ttl,
                        priority=entry.priority)
        client.records.create(dns_zone.id, record)

    def delete_entry(self, name, type, dns_zone=None):
        """Deletes an entry with the given name and type from a dns zone."""
        dns_zone = dns_zone or self.default_dns_zone
        records = self._get_records(dns_zone)
        matching_record = [rec for rec in records
                           if rec.name == name + '.' and rec.type == type]
        if not matching_record:
            raise exception.DnsRecordNotFound(name)
        LOG.debug("Deleting DNS entry %s.", name)
        self.dns_client.records.delete(dns_zone.id, matching_record[0].id)

    def get_entries_by_content(self, content, dns_zone=None):
        """Retrieves all entries in a DNS zone with matching content field."""
        records = self._get_records(dns_zone)
        return [self.converter.record_to_entry(record, dns_zone)
                for record in records if record.data == content]

    def get_entries_by_name(self, name, dns_zone):
        records = self._get_records(dns_zone)
        return [self.converter.record_to_entry(record, dns_zone)
                for record in records if record.name == name]

    def get_dns_zones(self, name=None):
        """Returns all dns zones (optionally filtered by the name argument."""
        domains = self.dns_client.domains.list()
        return [self.converter.domain_to_zone(domain)
                for domain in domains if not name or domain.name == name]

    def modify_content(self, name, content, dns_zone):
        # We dont need this in trove for now
        raise NotImplementedError(_("Not implemented for Designate DNS."))

    def rename_entry(self, content, name, dns_zone):
        # We dont need this in trove for now
        raise NotImplementedError(_("Not implemented for Designate DNS."))

    def _get_records(self, dns_zone):
        dns_zone = dns_zone or self.default_dns_zone
        if not dns_zone:
            raise TypeError(_('DNS domain is must be specified'))
        return self.dns_client.records.list(dns_zone.id)


class DesignateInstanceEntryFactory(driver.DnsInstanceEntryFactory):
    """Defines how instance DNS entries are created for instances."""

    def create_entry(self, instance_id):
        zone = DesignateDnsZone(id=DNS_DOMAIN_ID, name=DNS_DOMAIN_NAME)
        # Constructing the hostname by hashing the instance ID.
        name = encodeutils.to_utf8(instance_id)
        name = hashlib.md5(name).digest()
        name = base64.b32encode(name)[:11].lower()
        if six.PY3:
            name = name.decode('ascii')
        hostname = ("%s.%s" % (name, zone.name))
        # Removing the leading dot if present
        if hostname.endswith('.'):
            hostname = hostname[:-1]

        return driver.DnsEntry(name=hostname, content=None, type="A",
                               ttl=DNS_TTL, dns_zone=zone)


class DesignateDnsZone(driver.DnsZone):

    def __init__(self, id, name):
        self._name = name
        self._id = id

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    def __eq__(self, other):
        return (isinstance(other, DesignateDnsZone) and
                self.name == other.name and
                self.id == other.id)

    def __str__(self):
        return "%s:%s" % (self.id, self.name)
