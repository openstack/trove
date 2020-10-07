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

from trove.datastore.models import DatastoreVersion
from trove.tests.unittests.datastore.base import TestDatastoreBase


class TestDatastoreVersions(TestDatastoreBase):

    def test_load_datastore_version(self):
        datastore_version = DatastoreVersion.load(self.datastore,
                                                  self.ds_version_name)
        self.assertEqual(self.ds_version_name, datastore_version.name)

    def test_datastore_version_capabilities(self):
        self.datastore_version.capabilities.add(self.cap1, enabled=False)
        test_filtered_capabilities = self.capability_name_filter(
            self.datastore_version.capabilities)
        self.assertEqual(3, len(test_filtered_capabilities),
                         'Capabilities the test thinks it has are: %s, '
                         'Filtered capabilities: %s' %
                         (self.datastore_version.capabilities,
                          test_filtered_capabilities))

        # Test a fresh reloading of the datastore
        self.datastore_version = DatastoreVersion.load(self.datastore,
                                                       self.ds_version_name)
        test_filtered_capabilities = self.capability_name_filter(
            self.datastore_version.capabilities)
        self.assertEqual(3, len(test_filtered_capabilities),
                         'Capabilities the test thinks it has are: %s, '
                         'Filtered capabilities: %s' %
                         (self.datastore_version.capabilities,
                          test_filtered_capabilities))

        self.assertIn(self.cap2.name, self.datastore_version.capabilities)
        self.assertNotIn("non-existent", self.datastore_version.capabilities)
        self.assertIn(self.cap1.name, self.datastore_version.capabilities)
