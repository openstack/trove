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

from unittest import mock

from trove.common import clients
from trove.common import exception
from trove.datastore import models as datastore_models
from trove.tests.unittests.datastore.base import TestDatastoreBase


class TestDatastoreVersionMetadata(TestDatastoreBase):
    def setUp(self):
        super(TestDatastoreVersionMetadata, self).setUp()
        self.dsmetadata = datastore_models.DatastoreVersionMetadata
        self.volume_types = [
            {'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'name': 'type_1'},
            {'id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'name': 'type_2'},
            {'id': 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'name': 'type_3'},
        ]

    def tearDown(self):
        super(TestDatastoreVersionMetadata, self).tearDown()

    def test_map_flavors_to_datastore(self):
        datastore = datastore_models.Datastore.load(self.ds_name)
        ds_version = datastore_models.DatastoreVersion.load(
            datastore, self.ds_version_name)
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id,
            value=self.flavor_id, deleted=False, key='flavor')
        self.assertEqual(str(self.flavor_id), mapping.value)
        self.assertEqual(ds_version.id, mapping.datastore_version_id)
        self.assertEqual('flavor', str(mapping.key))

    def test_map_volume_types_to_datastores(self):
        datastore = datastore_models.Datastore.load(self.ds_name)
        ds_version = datastore_models.DatastoreVersion.load(
            datastore, self.ds_version_name)
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id,
            value=self.volume_type, deleted=False, key='volume_type')
        self.assertEqual(str(self.volume_type), mapping.value)
        self.assertEqual(ds_version.id, mapping.datastore_version_id)
        self.assertEqual('volume_type', str(mapping.key))

    def test_add_existing_flavor_associations(self):
        dsmetadata = datastore_models.DatastoreVersionMetadata
        self.assertRaisesRegex(
            exception.DatastoreFlavorAssociationAlreadyExists,
            "Flavor %s is already associated with datastore %s version %s"
            % (self.flavor_id, self.ds_name, self.ds_version_name),
            dsmetadata.add_datastore_version_flavor_association,
            self.ds_name, self.ds_version_name, [self.flavor_id])

    def test_add_existing_volume_type_associations(self):
        dsmetadata = datastore_models.DatastoreVersionMetadata
        self.assertRaises(
            exception.DatastoreVolumeTypeAssociationAlreadyExists,
            dsmetadata.add_datastore_version_volume_type_association,
            self.ds_name, self.ds_version_name, [self.volume_type])

    def test_delete_nonexistent_flavor_mapping(self):
        dsmeta = datastore_models.DatastoreVersionMetadata
        self.assertRaisesRegex(
            exception.DatastoreFlavorAssociationNotFound,
            "Flavor 2 is not supported for datastore %s version %s"
            % (self.ds_name, self.ds_version_name),
            dsmeta.delete_datastore_version_flavor_association,
            self.ds_name, self.ds_version_name, flavor_id=2)

    def test_delete_nonexistent_volume_type_mapping(self):
        dsmeta = datastore_models.DatastoreVersionMetadata
        self.assertRaises(
            exception.DatastoreVolumeTypeAssociationNotFound,
            dsmeta.delete_datastore_version_volume_type_association,
            self.ds_name, self.ds_version_name,
            volume_type_name='some random thing')

    def test_delete_flavor_mapping(self):
        flavor_id = 2
        dsmetadata = datastore_models.DatastoreVersionMetadata
        dsmetadata.add_datastore_version_flavor_association(
            self.ds_name,
            self.ds_version_name,
            [flavor_id])
        dsmetadata.delete_datastore_version_flavor_association(
            self.ds_name,
            self.ds_version_name,
            flavor_id)
        datastore = datastore_models.Datastore.load(self.ds_name)
        ds_version = datastore_models.DatastoreVersion.load(
            datastore,
            self.ds_version_name)
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id, value=flavor_id, key='flavor')
        self.assertTrue(mapping.deleted)
        # check update
        dsmetadata.add_datastore_version_flavor_association(
            self.ds_name, self.ds_version_name, [flavor_id])
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id, value=flavor_id, key='flavor')
        self.assertFalse(mapping.deleted)
        # clear the mapping
        datastore_models.DatastoreVersionMetadata. \
            delete_datastore_version_flavor_association(self.ds_name,
                                                        self.ds_version_name,
                                                        flavor_id)

    def test_delete_volume_type_mapping(self):
        volume_type = 'this is bogus'
        dsmetadata = datastore_models.DatastoreVersionMetadata
        dsmetadata.add_datastore_version_volume_type_association(
            self.ds_name,
            self.ds_version_name,
            [volume_type])
        dsmetadata.delete_datastore_version_volume_type_association(
            self.ds_name,
            self.ds_version_name,
            volume_type)
        datastore = datastore_models.Datastore.load(self.ds_name)
        ds_version = datastore_models.DatastoreVersion.load(
            datastore,
            self.ds_version_name)
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id, value=volume_type,
            key='volume_type')
        self.assertTrue(mapping.deleted)
        # check update
        dsmetadata.add_datastore_version_volume_type_association(
            self.ds_name, self.ds_version_name, [volume_type])
        mapping = datastore_models.DBDatastoreVersionMetadata.find_by(
            datastore_version_id=ds_version.id, value=volume_type,
            key='volume_type')
        self.assertFalse(mapping.deleted)
        # clear the mapping
        dsmetadata.delete_datastore_version_volume_type_association(
            self.ds_name,
            self.ds_version_name,
            volume_type)

    @mock.patch.object(datastore_models.DatastoreVersionMetadata,
                       '_datastore_version_find')
    @mock.patch.object(datastore_models.DatastoreVersionMetadata,
                       'list_datastore_version_volume_type_associations')
    @mock.patch.object(clients, 'create_cinder_client')
    def _mocked_allowed_datastore_version_volume_types(self,
                                                       trove_volume_types,
                                                       mock_cinder_client,
                                                       mock_list, *args):
        """Call this with a list of strings specifying volume types."""
        cinder_vts = []
        for vt in self.volume_types:
            cinder_type = mock.Mock()
            cinder_type.id = vt.get('id')
            cinder_type.name = vt.get('name')
            cinder_vts.append(cinder_type)
        mock_cinder_client.return_value.volume_types.list.return_value = (
            cinder_vts)

        mock_trove_list_result = mock.MagicMock()
        mock_trove_list_result.count.return_value = len(trove_volume_types)
        mock_trove_list_result.__iter__.return_value = []
        for trove_vt in trove_volume_types:
            trove_type = mock.Mock()
            trove_type.value = trove_vt
            mock_trove_list_result.__iter__.return_value.append(trove_type)
        mock_list.return_value = mock_trove_list_result

        return self.dsmetadata.allowed_datastore_version_volume_types(
            None, 'ds', 'dsv')

    def _assert_equal_types(self, test_dict, output_obj):
        self.assertEqual(test_dict.get('id'), output_obj.id)
        self.assertEqual(test_dict.get('name'), output_obj.name)

    def test_allowed_volume_types_from_ids(self):
        id1 = self.volume_types[0].get('id')
        id2 = self.volume_types[1].get('id')
        res = self._mocked_allowed_datastore_version_volume_types([id1, id2])
        self._assert_equal_types(self.volume_types[0], res[0])
        self._assert_equal_types(self.volume_types[1], res[1])

    def test_allowed_volume_types_from_names(self):
        name1 = self.volume_types[0].get('name')
        name2 = self.volume_types[1].get('name')
        res = self._mocked_allowed_datastore_version_volume_types([name1,
                                                                   name2])
        self._assert_equal_types(self.volume_types[0], res[0])
        self._assert_equal_types(self.volume_types[1], res[1])

    def test_allowed_volume_types_no_restrictions(self):
        res = self._mocked_allowed_datastore_version_volume_types([])
        self._assert_equal_types(self.volume_types[0], res[0])
        self._assert_equal_types(self.volume_types[1], res[1])
        self._assert_equal_types(self.volume_types[2], res[2])
