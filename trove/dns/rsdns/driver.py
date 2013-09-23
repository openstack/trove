# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack Foundation
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
Dns Driver that uses Rackspace DNSaaS.
"""

__version__ = '2.4'

import hashlib

from trove.openstack.common import log as logging
from trove.common import cfg
from trove.common import exception
from trove.common.exception import NotFound
from trove.dns.models import DnsRecord
from rsdns.client import DNSaas
from rsdns.client.future import RsDnsError

from trove.dns.driver import DnsEntry

CONF = cfg.CONF

DNS_HOSTNAME = CONF.dns_hostname
DNS_ACCOUNT_ID = CONF.dns_account_id
DNS_AUTH_URL = CONF.dns_auth_url
DNS_DOMAIN_NAME = CONF.dns_domain_name
DNS_USERNAME = CONF.dns_username
DNS_PASSKEY = CONF.dns_passkey
DNS_MANAGEMENT_BASE_URL = CONF.dns_management_base_url
DNS_TTL = CONF.dns_ttl
DNS_DOMAIN_ID = CONF.dns_domain_id


LOG = logging.getLogger(__name__)


class EntryToRecordConverter(object):

    def __init__(self, default_dns_zone):
        self.default_dns_zone = default_dns_zone

    def domain_to_dns_zone(self, domain):
        return RsDnsZone(id=domain.id, name=domain.name)

    def name_to_long_name(self, name, dns_zone=None):
        dns_zone = dns_zone or self.default_dns_zone
        if name:
            long_name = name + "." + dns_zone.name
        else:
            long_name = ""
        return long_name

    def record_to_entry(self, record, dns_zone):
        entry_name = record.name
        return DnsEntry(name=entry_name, content=record.data,
                        type=record.type, ttl=record.ttl, dns_zone=dns_zone)


def create_client_with_flag_values():
    """Creates a RS DNSaaS client using the Flag values."""
    if DNS_MANAGEMENT_BASE_URL is None:
        raise RuntimeError("Missing flag value for dns_management_base_url.")
    return DNSaas(DNS_ACCOUNT_ID, DNS_USERNAME, DNS_PASSKEY,
                  auth_url=DNS_AUTH_URL,
                  management_base_url=DNS_MANAGEMENT_BASE_URL)


def find_default_zone(dns_client, raise_if_zone_missing=True):
    """Using the domain_name from the FLAG values, creates a zone.

    Because RS DNSaaS needs the ID, we need to find this value before we start.
    In testing it's difficult to keep up with it because the database keeps
    getting wiped... maybe later we could go back to storing it as a FLAG value

    """
    domain_name = DNS_DOMAIN_NAME
    try:
        domains = dns_client.domains.list(name=domain_name)
        for domain in domains:
            if domain.name == domain_name:
                return RsDnsZone(id=domain.id, name=domain_name)
    except NotFound:
        pass
    if not raise_if_zone_missing:
        return RsDnsZone(id=None, name=domain_name)
    msg = ("The dns_domain_name from the FLAG values (%s) "
           "does not exist!  account_id=%s, username=%s, LIST=%s")
    params = (domain_name, DNS_ACCOUNT_ID, DNS_USERNAME, domains)
    raise RuntimeError(msg % params)


class RsDnsDriver(object):
    """Uses RS DNSaaS"""

    def __init__(self, raise_if_zone_missing=True):
        self.dns_client = create_client_with_flag_values()
        self.dns_client.authenticate()
        self.default_dns_zone = RsDnsZone(id=DNS_DOMAIN_ID,
                                          name=DNS_DOMAIN_NAME)
        self.converter = EntryToRecordConverter(self.default_dns_zone)
        if DNS_TTL < 300:
            msg = "TTL value '--dns_ttl=%s' should be greater than 300"
            raise Exception(msg % DNS_TTL)

    def create_entry(self, entry):
        dns_zone = entry.dns_zone or self.default_dns_zone
        if dns_zone.id is None:
            raise TypeError("The entry's dns_zone must have an ID specified.")
        name = entry.name  # + "." + dns_zone.name
        LOG.debug("Going to create RSDNS entry %s." % name)
        try:
            future = self.dns_client.records.create(
                domain=dns_zone.id,
                record_name=name,
                record_data=entry.content,
                record_type=entry.type,
                record_ttl=entry.ttl)
            try:
                #TODO: Bring back our good friend poll_until.
                while(future.ready is False):
                    import time
                    time.sleep(2)
                    LOG.info("Waiting for the dns record_id.. ")

                if len(future.resource) < 1:
                    raise RsDnsError("No DNS records were created.")
                elif len(future.resource) > 1:
                    LOG.error("More than one DNS record created. Ignoring.")
                actual_record = future.resource[0]
                DnsRecord.create(name=name, record_id=actual_record.id)
                LOG.debug("Added RS DNS entry.")
            except RsDnsError as rde:
                LOG.error("An error occurred creating DNS entry!")
                raise
        except Exception as ex:
            LOG.error("Error when creating a DNS record!")
            raise

    def delete_entry(self, name, type, dns_zone=None):
        dns_zone = dns_zone or self.default_dns_zone
        long_name = name
        db_record = DnsRecord.find_by(name=name)
        record = self.dns_client.records.get(
            domain_id=dns_zone.id,
            record_id=db_record.record_id)
        if record.name != name or record.type != 'A':
            LOG.error("Tried to delete DNS record with name=%s, id=%s, but the"
                      " database returned a DNS record with the name %s and "
                      "type %s." % (name, db_record.id, record.name,
                                    record.type))
            raise exception.DnsRecordNotFound(name)
        self.dns_client.records.delete(
            domain_id=dns_zone.id,
            record_id=record.id)
        db_record.delete()

    def get_entries(self, name=None, content=None, dns_zone=None):
        dns_zone = dns_zone or self.defaucreate_entrylt_dns_zone
        long_name = name  # self.converter.name_to_long_name(name)
        records = self.dns_client.records.list(
            domain_id=dns_zone.id,
            record_name=long_name,
            record_address=content)
        return [self.converter.record_to_entry(record, dns_zone)
                for record in records]

    def get_entries_by_content(self, content, dns_zone=None):
        return self.get_entries(content=content)

    def get_entries_by_name(self, name, dns_zone=None):
        return self.get_entries(name=name, dns_zone=dns_zone)

    def get_dns_zones(self, name=None):
        domains = self.dns_client.domains.list(name=name)
        return [self.converter.domain_to_dns_zone(domain)
                for domain in domains]

    def modify_content(self, *args, **kwargs):
        raise NotImplementedError("Not implemented for RS DNS.")

    def rename_entry(self, *args, **kwargs):
        raise NotImplementedError("Not implemented for RS DNS.")


class RsDnsInstanceEntryFactory(object):
    """Defines how instance DNS entries are created for instances."""

    def __init__(self, dns_domain_id=None):
        dns_domain_id = dns_domain_id or DNS_DOMAIN_ID
        self.default_dns_zone = RsDnsZone(id=dns_domain_id,
                                          name=DNS_DOMAIN_NAME)

    def create_entry(self, instance_id):
        id = instance_id
        hostname = ("%s.%s" % (hashlib.sha1(id).hexdigest(),
                               self.default_dns_zone.name))
        return DnsEntry(name=hostname, content=None, type="A", ttl=DNS_TTL,
                        dns_zone=self.default_dns_zone)


class RsDnsZone(object):

    def __init__(self, id, name):
        self.name = name
        self.id = id

    def __eq__(self, other):
        return (isinstance(other, RsDnsZone) and
                self.name == other.name and
                self.id == other.id)

    def __str__(self):
        return "%s:%s" % (self.id, self.name)
