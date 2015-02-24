#    Copyright (c) 2014 Rackspace Hosting
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

from trove.tests.unittests.datastore.base import TestDatastoreBase
from trove.datastore.models import CapabilityOverride
from trove.datastore.models import Capability
from trove.common.exception import CapabilityNotFound


class TestCapabilities(TestDatastoreBase):
    def setUp(self):
        super(TestCapabilities, self).setUp()

    def tearDown(self):
        super(TestCapabilities, self).tearDown()

    def test_capability(self):
        cap = Capability.load(self.capability_name)
        self.assertEqual(self.capability_name, cap.name)
        self.assertEqual(self.capability_desc, cap.description)
        self.assertEqual(self.capability_enabled, cap.enabled)

    def test_ds_capability_create_disabled(self):
        self.ds_cap = CapabilityOverride.create(
            self.cap1, self.datastore_version.id, enabled=False)
        self.assertFalse(self.ds_cap.enabled)

        self.ds_cap.delete()

    def test_capability_enabled(self):
        self.assertTrue(Capability.load(self.capability_name).enabled)

    def test_capability_disabled(self):
        capability = Capability.load(self.capability_name)
        capability.disable()
        self.assertFalse(capability.enabled)

        self.assertFalse(Capability.load(self.capability_name).enabled)

    def test_load_nonexistent_capability(self):
        self.assertRaises(CapabilityNotFound, Capability.load, "non-existent")
