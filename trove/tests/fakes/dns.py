#    Copyright 2014 Rackspace
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

from oslo_log import log as logging
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis.asserts import fail

from trove.dns import driver


LOG = logging.getLogger(__name__)
ENTRIES = {}


class FakeDnsDriver(driver.DnsDriver):

    def create_entry(self, entry, content):
        """Pretend to create a DNS entry somewhere.

        Since nothing else tests that this works, there's nothing more to do
        here.

        """
        entry.content = content
        assert_true(entry.name not in ENTRIES)
        LOG.debug("Adding fake DNS entry for hostname %s." % entry.name)
        ENTRIES[entry.name] = entry

    def delete_entry(self, name, type, dns_zone=None):
        LOG.debug("Deleting fake DNS entry for hostname %s" % name)
        ENTRIES.pop(name, None)


class FakeDnsInstanceEntryFactory(driver.DnsInstanceEntryFactory):

    def create_entry(self, instance_id):
        # Construct hostname using pig-latin.
        hostname = "%s-lay" % instance_id
        LOG.debug("Mapping instance_id %s to hostname %s"
                  % (instance_id, hostname))
        return driver.DnsEntry(name=hostname, content=None,
                               type="A", ttl=42, dns_zone=None)


class FakeDnsChecker(object):
    """Used by tests to make sure a DNS record was written in fake mode."""

    def __call__(self, mgmt_instance):
        """
        Given an instance ID and ip address, confirm that the proper DNS
        record was stored in Designate or some other DNS system.
        """
        entry = FakeDnsInstanceEntryFactory().create_entry(mgmt_instance.id)
        # Confirm DNS entry shown to user is what we expect.
        assert_equal(entry.name, mgmt_instance.hostname)
        hostname = entry.name
        for i in ENTRIES:
            print(i)
            print("\t%s" % ENTRIES[i])
        assert_true(hostname in ENTRIES,
                    "Hostname %s not found in DNS entries!" % hostname)
        entry = ENTRIES[hostname]
        # See if the ip address assigned to the record is what we expect.
        # This isn't perfect, but for Fake Mode its good enough. If we
        # really want to know exactly what it should be then we should restore
        # the ability to return the IP from the API as well as a hostname,
        # since that lines up to the DnsEntry's content field.
        ip_addresses = mgmt_instance.server['addresses']
        for network_name, ip_list in ip_addresses.items():
            for ip in ip_list:
                if entry.content == ip['addr']:
                    return
        fail("Couldn't find IP address %s among these values: %s"
             % (entry.content, ip_addresses))
