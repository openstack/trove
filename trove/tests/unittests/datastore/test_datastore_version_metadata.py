# Copyright (c) 2015 Rackspace Hosting
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from trove.common import exception
from trove.datastore import models as datastore_models
from trove.tests.unittests.datastore.base import TestDatastoreBase


class TestDatastoreVersionMetadata(TestDatastoreBase):
    def setUp(self):
        super(TestDatastoreVersionMetadata, self).setUp()

    def tearDown(self):
        super(TestDatastoreVersionMetadata, self).tearDown()

    def test_map_flavors_to_datastore(self):
        datastore = datastore_models.Datastore.load(self.ds_name)
        ds_version = datastore_models.DatastoreVersion.load(datastore,
                                                            self.ds_version)
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id,
            value=self.flavor_id, deleted=False, key='flavor')
        self.assertEqual(str(self.flavor_id), mapping.value)
        self.assertEqual(ds_version.id, mapping.datastore_version_id)
        self.assertEqual('flavor', str(mapping.key))

    def test_add_existing_associations(self):
        dsmetadata = datastore_models.DatastoreVersionMetadata
        self.assertRaisesRegexp(
            exception.DatastoreFlavorAssociationAlreadyExists,
            "Flavor %s is already associated with datastore %s version %s"
            % (self.flavor_id, self.ds_name, self.ds_version),
            dsmetadata.add_datastore_version_flavor_association,
            self.ds_name, self.ds_version, [self.flavor_id])

    def test_delete_nonexistent_mapping(self):
        dsmeta = datastore_models.DatastoreVersionMetadata
        self.assertRaisesRegexp(
            exception.DatastoreFlavorAssociationNotFound,
            "Flavor 2 is not supported for datastore %s version %s"
            % (self.ds_name, self.ds_version),
            dsmeta.delete_datastore_version_flavor_association,
            self.ds_name, self.ds_version, flavor_id=2)

    def test_delete_mapping(self):
        flavor_id = 2
        dsmetadata = datastore_models. DatastoreVersionMetadata
        dsmetadata.add_datastore_version_flavor_association(self.ds_name,
                                                            self.ds_version,
                                                            [flavor_id])
        dsmetadata.delete_datastore_version_flavor_association(self.ds_name,
                                                               self.ds_version,
                                                               flavor_id)
        datastore = datastore_models.Datastore.load(self.ds_name)
        ds_version = datastore_models.DatastoreVersion.load(datastore,
                                                            self.ds_version)
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id, value=flavor_id, key='flavor')
        self.assertTrue(mapping.deleted)
        # check update
        dsmetadata.add_datastore_version_flavor_association(
            self.ds_name, self.ds_version, [flavor_id])
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id, value=flavor_id, key='flavor')
        self.assertFalse(mapping.deleted)
        # clear the mapping
        datastore_models.DatastoreVersionMetadata.\
            delete_datastore_version_flavor_association(self.ds_name,
                                                        self.ds_version,
                                                        flavor_id)
