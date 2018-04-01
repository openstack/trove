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
"""Tests classes which convert RS style-entries to Nova DNS entries."""

import hashlib
import unittest
from proboscis import test

from trove.tests.config import CONFIG


if CONFIG.white_box:
    from nova import flags
    from rsdns.client.records import Record
    from trove.dns.rsdns.driver import EntryToRecordConverter
    from trove.dns.rsdns.driver import RsDnsInstanceEntryFactory
    from trove.dns.rsdns.driver import RsDnsZone
    FLAGS = flags.FLAGS
    driver = None
    DEFAULT_ZONE = RsDnsZone(1, "dbaas.rackspace.org")
    TEST_CONTENT = "126.1.1.1"
    TEST_NAME = "hiwassup.dbaas.rackspace.org"


@test(groups=["unit", "rsdns.conversion"],
      enabled=CONFIG.white_box)
class ConvertingNovaEntryNamesToRecordNames(unittest.TestCase):

    def setUp(self):
        self.converter = EntryToRecordConverter(DEFAULT_ZONE)
        self.fake_zone = RsDnsZone(id=5, name="blah.org")

    def test_normal_name(self):
        long_name = self.converter.name_to_long_name("hi", self.fake_zone)
        self.assertEqual("hi.blah.org", long_name)

    def test_short_name(self):
        long_name = self.converter.name_to_long_name("", self.fake_zone)
        self.assertEqual("", long_name)

    def test_long_name(self):
        long_name = self.converter.name_to_long_name("blah.org.",
                                                     self.fake_zone)
        self.assertEqual("blah.org..blah.org", long_name)


@test(groups=["unit", "rsdns.conversion"],
      enabled=CONFIG.white_box)
class ConvertingRecordsToEntries(unittest.TestCase):

    def setUp(self):
        self.converter = EntryToRecordConverter(DEFAULT_ZONE)
        self.fake_zone = RsDnsZone(id=5, name="blah.org")

    def test_normal_name(self):
        record = Record(None, {"id": 5, "name": "hi.blah.org",
                               "data": "stacker.com blah@blah 13452378",
                               "ttl": 5,
                               "type": "SOA"})
        entry = self.converter.record_to_entry(record=record,
                                               dns_zone=self.fake_zone)
        self.assertEqual("stacker.com blah@blah 13452378", entry.content)
        self.assertEqual("hi.blah.org", entry.name)
        self.assertEqual("5", str(entry.ttl))
        self.assertEqual("SOA", entry.type)


@test(groups=["rsdns.conversion"],
      enabled=CONFIG.white_box)
class WhenCreatingAnEntryForAnInstance(unittest.TestCase):
    # This isn't a unit test because RsDnsInstanceEntryFactory connects to the
    # service.

    def setUp(self):
        self.creator = RsDnsInstanceEntryFactory()

    def test_should_concatanate_strings(self):
        instance = {'id': '56',
                    'uuid': '000136c0-effa-4711-a747-a5b9fbfcb3bd'}
        entry = self.creator.create_entry(instance)
        expected_name = "%s.%s" % (hashlib.sha1(instance['uuid']).hexdigest(),
                                   FLAGS.dns_domain_name)
        self.assertEqual(expected_name, entry.name,
                         msg="Entry name should match - %s" % entry.name)
        self.assertIsNone(entry.content)
        self.assertEqual("A", entry.type)
        self.assertEqual(FLAGS.dns_ttl, entry.ttl)
        self.assertIsNone(entry.priority)
        self.assertEqual(FLAGS.dns_domain_name, entry.dns_zone.name)
        if not entry.dns_zone.id:
            self.fail(msg="DNS Zone Id should not be empty")
