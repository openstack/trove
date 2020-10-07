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

from trove.datastore import models as datastore_models
from trove.datastore.models import Capability
from trove.datastore.models import Datastore
from trove.datastore.models import DatastoreVersion
from trove.datastore.models import DatastoreVersionMetadata
from trove.datastore.models import DBCapabilityOverrides
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestDatastoreBase(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()

        cls.ds_name = cls.random_name(name='test-datastore')
        cls.ds_version_name = cls.random_name(name='test-version')
        cls.capability_name = cls.random_name(name='root_on_create',
                                              prefix='TestDatastoreBase')
        cls.capability_desc = "Enables root on create"
        cls.capability_enabled = True
        cls.flavor_id = 1
        cls.volume_type = 'some-valid-volume-type'

        datastore_models.update_datastore(cls.ds_name, False)
        cls.datastore = Datastore.load(cls.ds_name)

        datastore_models.update_datastore_version(
            cls.ds_name, cls.ds_version_name, "mysql", "", "", "", True)
        DatastoreVersionMetadata.add_datastore_version_flavor_association(
            cls.ds_name, cls.ds_version_name, [cls.flavor_id])
        DatastoreVersionMetadata.add_datastore_version_volume_type_association(
            cls.ds_name, cls.ds_version_name, [cls.volume_type])

        cls.datastore_version = DatastoreVersion.load(cls.datastore,
                                                      cls.ds_version_name)
        cls.test_id = cls.datastore_version.id

        cls.cap1 = Capability.create(cls.capability_name,
                                     cls.capability_desc, True)
        cls.cap2 = Capability.create(
            cls.random_name(name='require_volume', prefix='TestDatastoreBase'),
            "Require external volume", True)
        cls.cap3 = Capability.create(
            cls.random_name(name='test_capability',
                            prefix='TestDatastoreBase'),
            "Test capability", False)

        super(TestDatastoreBase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        capabilities_overridden = DBCapabilityOverrides.find_all(
            datastore_version_id=cls.test_id).all()
        for ce in capabilities_overridden:
            ce.delete()

        cls.cap1.delete()
        cls.cap2.delete()
        cls.cap3.delete()

        datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=cls.test_id).delete()
        cls.datastore_version.delete()
        cls.datastore.delete()

        super(TestDatastoreBase, cls).tearDownClass()

    def capability_name_filter(self, capabilities):
        new_capabilities = []
        for capability in capabilities:
            if 'TestDatastoreBase' in capability.name:
                new_capabilities.append(capability)
        return new_capabilities
