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
"""
This test recreates an issue we had with eventlet. In the logs, we'd see that
the JSON response was malformed; instead of JSON, it contained the following
string:
Second simultaneous read on fileno 5 detected.  Unless you really know what
you're doing, make sure that only one greenthread can read any particular
socket.  Consider using a pools.Pool. If you do know what you're doing and want
to disable this error, call
eventlet.debug.hub_multiple_reader_prevention(False)

It is perhaps the most helpful error message ever created.

The root issue was that a subclass of httplib2.Http was created at program
started and used in all threads.

Using the old (broken) RsDNS client code this test recreates the greatest error
message ever.
"""

try:
    import eventlet
    CAN_USE_EVENTLET = True
except ImportError:
    CAN_USE_EVENTLET = False
import uuid

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_true

from trove.tests.config import CONFIG

WHITE_BOX = CONFIG.white_box
RUN_DNS = CONFIG.values.get("trove_dns_support", False)


if CONFIG.white_box:
    from trove.dns.rsdns.driver import RsDnsInstanceEntryFactory
    from nova import flags
    from nova import utils
    FLAGS = flags.FLAGS


@test(groups=["rsdns.eventlet"], enabled=CAN_USE_EVENTLET)
class RsdnsEventletTests(object):
    """Makes sure the RSDNS client can be used from multiple green threads."""

    def assert_record_created(self, index):
        msg = "Record %d wasn't created!" % index
        assert_true(index in self.new_records, msg)

    @before_class(enabled=WHITE_BOX and RUN_DNS)
    def create_driver(self):
        """Creates the DNS Driver used in subsequent tests."""
        self.driver = utils.import_object(FLAGS.dns_driver)
        self.entry_factory = RsDnsInstanceEntryFactory()
        self.test_uuid = uuid.uuid4().hex
        self.new_records = {}

    def make_record(self, index):
        """Creates a record with the form 'eventlet-%s-%d'."""
        uuid = "eventlet-%s-%d" % (self.test_uuid, index)
        instance = {'uuid': uuid}
        entry = self.entry_factory.create_entry(instance)
        entry.name = uuid + "." + self.entry_factory.default_dns_zone.name
        entry.content = "123.123.123.123"
        self.driver.create_entry(entry)
        self.new_records[index] = True

    @test(enabled=WHITE_BOX and RUN_DNS)
    def use_dns_from_a_single_thread(self):
        """Add DNS records one at a time."""
        self.new_records = {}
        for index in range(-1, -5, -1):
            self.make_record(index)
            self.assert_record_created(index)

    @test(enabled=WHITE_BOX and RUN_DNS)
    def use_dns_from_multiple_greenthreads(self):
        """Add multiple DNS records at once."""
        self.new_records = {}

        def make_record(index):
            def __cb():
                self.make_record(index)
                self.assert_record_created(index)
                return index
            return __cb

        pile = eventlet.GreenPile()
        indices = range(1, 4)
        for index in indices:
            pile.spawn(make_record(index))

        list(pile)  # Wait for them to finish
        for index in indices:
            self.assert_record_created(index)
