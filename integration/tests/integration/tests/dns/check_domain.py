# Copyright 2011 OpenStack LLC.
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
"""Checks that the domain specified in the flag file exists and is valid.

If you define the environment variable ADD_DOMAINS=True when running the tests,
they will create the domain if its not found (see below for details).

"""
import time
from proboscis import test
from proboscis import before_class
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.decorators import time_out

from trove.tests.config import CONFIG

WHITE_BOX = CONFIG.white_box
RUN_DNS = CONFIG.values.get("trove_dns_support", False)

if WHITE_BOX:
    from nova import utils
    from nova import flags
    import rsdns
    from trove.dns.rsdns.driver import create_client_with_flag_values
    from trove.dns.driver import DnsEntry
    from trove.dns.rsdns.driver import RsDnsInstanceEntryFactory
    from trove.dns.rsdns.driver import RsDnsDriver
    from trove.dns.rsdns.driver import RsDnsZone
    from trove.utils import poll_until
    FLAGS = flags.FLAGS
    TEST_CONTENT = "126.1.1.1"
    TEST_NAME = "hiwassup.%s" % FLAGS.dns_domain_name
    DNS_DOMAIN_ID = None


@test(groups=["rsdns.domains", "rsdns.show_entries"],
      enabled=WHITE_BOX and RUN_DNS)
class ClientTests(object):

    @before_class
    def increase_logging(self):
        import httplib2
        httplib2.debuglevel = 1

    @test
    def can_auth(self):
        self.client = create_client_with_flag_values()
        self.client.authenticate()

    @test(depends_on=[can_auth])
    def list_domains(self):
        domains = self.client.domains.list()
        print(domains)


@test(groups=["rsdns.domains"], depends_on=[ClientTests],
      enabled=WHITE_BOX and RUN_DNS)
class RsDnsDriverTests(object):
    """Tests the RS DNS Driver."""

    def create_domain_if_needed(self):
        """Adds the domain specified in the flags."""
        print("Creating domain %s" % self.driver.default_dns_zone.name)
        future = self.driver.dns_client.domains.create(
            self.driver.default_dns_zone.name)
        while not future.ready:
            time.sleep(2)
        print("Got something: %s" % future.resource)
        with open('/home/vagrant/dns_resource.txt', 'w') as f:
            f.write('%r\n' % future.result[0].id)
        global DNS_DOMAIN_ID
        DNS_DOMAIN_ID = future.result[0].id
        print("The domain should have been created with id=%s" % DNS_DOMAIN_ID)

    @test
    @time_out(2 * 60)
    def ensure_domain_specified_in_flags_exists(self):
        """Make sure the domain in the FLAGS exists."""
        self.driver = RsDnsDriver(raise_if_zone_missing=False)
        assert_not_equal(None, self.driver.default_dns_zone)

        def zone_found():
            zones = self.driver.get_dns_zones()
            print("Retrieving zones.")
            for zone in zones:
                print("zone %s" % zone)
                if zone.name == self.driver.default_dns_zone.name:
                    self.driver.default_dns_zone.id = zone.id
                    global DNS_DOMAIN_ID
                    DNS_DOMAIN_ID = zone.id
                    return True
            return False
        if zone_found():
            return
        self.create_domain_if_needed()
        for i in range(5):
            if zone_found():
                return
        self.fail("""Could not find default dns zone.
                  This happens when they clear the staging DNS service of data.
                  To fix it, manually run the tests as follows:
                  $ ADD_DOMAINS=True python int_tests.py
                  and if all goes well the tests will create a new domain
                  record.""")

    @test(depends_on=[ensure_domain_specified_in_flags_exists],
          enabled=WHITE_BOX and FLAGS.dns_domain_name != "dbaas.rackspace.com")
    def delete_all_entries(self):
        """Deletes all entries under the default domain."""
        list = self.driver.get_entries()
        for entry in list:
            if entry.type == "A":
                self.driver.delete_entry(name=entry.name, type=entry.type,
                                         dns_zone=entry.dns_zone)
        # It takes awhile for them to be deleted.
        poll_until(lambda: self.driver.get_entries_by_name(TEST_NAME),
                   lambda list: len(list) == 0,
                   sleep_time=4, time_out=60)

    @test(depends_on=[delete_all_entries])
    def create_test_entry(self):
        fullname = TEST_NAME
        entry = DnsEntry(name=fullname, content=TEST_CONTENT, type="A",
                         ttl=3600)
        self.driver.create_entry(entry)
        list = None
        for i in range(500):
            list = self.driver.get_entries_by_name(name=fullname)
            if len(list) > 0:
                break
            time.sleep(1)
        print("This is the list: %r" % list)
        assert_equal(1, len(list))
        list2 = self.driver.get_entries_by_content(content=TEST_CONTENT)
        assert_equal(1, len(list2))

    @test(depends_on=[delete_all_entries])
    def create_test_rsdns_entry(self):
        """Create an entry using the RsDnsInstanceEntryFactory."""
        instance = {'uuid': '000136c0-effa-4711-a747-a5b9fbfcb3bd', 'id': '10'}
        ip = "10.100.2.7"
        factory = RsDnsInstanceEntryFactory(dns_domain_id=DNS_DOMAIN_ID)
        entry = factory.create_entry(instance)
        entry.content = ip
        self.driver.create_entry(entry)
        entries = self.driver.get_entries_by_name(name=entry.name)
        assert_equal(1, len(entries))
        assert_equal(ip, entries[0].content)
        assert_equal(FLAGS.dns_ttl, entries[0].ttl)

    @test(depends_on=[create_test_entry])
    def delete_test_entry(self):
        fullname = TEST_NAME
        self.driver.delete_entry(fullname, "A")
        # It takes awhile for them to be deleted.
        poll_until(lambda: self.driver.get_entries_by_name(TEST_NAME),
                   lambda list: len(list) == 0,
                   sleep_time=2, time_out=60)
