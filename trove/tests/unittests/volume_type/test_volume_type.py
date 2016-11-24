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

from trove.common import remote
from trove.tests.unittests import trove_testtools
from trove.volume_type import models


class TestVolumeType(trove_testtools.TestCase):

    def test_volume_type(self):
        cinder_volume_type = mock.MagicMock()
        cinder_volume_type.id = 123
        cinder_volume_type.name = 'test_type'
        cinder_volume_type.is_public = True
        cinder_volume_type.description = 'Test volume type'

        volume_type = models.VolumeType(cinder_volume_type)

        self.assertEqual(cinder_volume_type.id, volume_type.id)
        self.assertEqual(cinder_volume_type.name, volume_type.name)
        self.assertEqual(cinder_volume_type.is_public, volume_type.is_public)
        self.assertEqual(cinder_volume_type.description,
                         volume_type.description)

    @mock.patch.object(remote, 'create_cinder_client')
    def test_volume_types(self, mock_client):
        mock_context = mock.MagicMock()
        mock_types = [mock.MagicMock(), mock.MagicMock()]

        mock_client(mock_context).volume_types.list.return_value = mock_types

        volume_types = models.VolumeTypes(mock_context)

        for i, volume_type in enumerate(volume_types):
            self.assertEqual(mock_types[i], volume_type.volume_type,
                             "Volume type {} does not match.".format(i))
