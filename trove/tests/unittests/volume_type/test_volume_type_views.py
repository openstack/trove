# Copyright 2016 Tesora, Inc.
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
#

import mock

from trove.tests.unittests import trove_testtools
from trove.volume_type import views


class TestVolumeTypeViews(trove_testtools.TestCase):

    def test_volume_type_view(self):
        test_id = 'test_id'
        test_name = 'test_name'
        test_is_public = True
        test_description = 'Test description'
        test_req = mock.MagicMock()

        volume_type = mock.MagicMock()
        volume_type.id = test_id
        volume_type.name = test_name
        volume_type.is_public = test_is_public
        volume_type.description = test_description

        volume_type_view = views.VolumeTypeView(volume_type, req=test_req)
        data = volume_type_view.data()

        self.assertEqual(volume_type, volume_type_view.volume_type)
        self.assertEqual(test_req, volume_type_view.req)
        self.assertEqual(test_id, data['volume_type']['id'])
        self.assertEqual(test_name, data['volume_type']['name'])
        self.assertEqual(test_is_public, data['volume_type']['is_public'])
        self.assertEqual(test_description, data['volume_type']['description'])
        self.assertEqual(test_req, volume_type_view.req)

    @mock.patch.object(views, 'VolumeTypeView')
    def test_volume_types_view(self, mock_single_view):
        test_type_1 = mock.MagicMock()
        test_type_2 = mock.MagicMock()

        volume_types_view = views.VolumeTypesView([test_type_1, test_type_2])

        self.assertEqual(
            {'volume_types': [
                mock_single_view(test_type_1, None).data()['volume_type'],
                mock_single_view(test_type_2, None).data()['volume_type']]},
            volume_types_view.data())
