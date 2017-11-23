# Copyright 2016 Tesora Inc.
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

from mock import ANY
from mock import call
from mock import DEFAULT
from mock import MagicMock
from mock import Mock
from mock import patch
from mock import PropertyMock

from trove.cluster import models
from trove.common import exception
from trove.common import remote
from trove.tests.unittests import trove_testtools


class TestModels(trove_testtools.TestCase):

    @patch.object(remote, 'create_nova_client', return_value=MagicMock())
    def test_validate_instance_flavors(self, create_nova_cli_mock):
        patch.object(
            create_nova_cli_mock.return_value, 'flavors',
            new_callable=PropertyMock(return_value=Mock()))
        mock_flv = create_nova_cli_mock.return_value.flavors.get.return_value
        mock_flv.ephemeral = 0

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 1.5,
                           'region_name': 'home'},
                          {'flavor_id': 2, 'volume_size': 3,
                           'region_name': 'work'}]
        models.validate_instance_flavors(Mock(), test_instances,
                                         True, True)
        create_nova_cli_mock.assert_has_calls([call(ANY, None),
                                               call(ANY, 'home'),
                                               call(ANY, 'work')])

        self.assertRaises(exception.LocalStorageNotSpecified,
                          models.validate_instance_flavors,
                          Mock(), test_instances, False, True)

        mock_flv.ephemeral = 1
        models.validate_instance_flavors(Mock(), test_instances,
                                         False, True)

    def test_validate_volume_size(self):
        self.patch_conf_property('max_accepted_volume_size', 10)
        models.validate_volume_size(9)
        models.validate_volume_size(10)

        self.assertRaises(exception.VolumeQuotaExceeded,
                          models.validate_volume_size, 11)

        self.assertRaises(exception.VolumeSizeNotSpecified,
                          models.validate_volume_size, None)

    @patch.object(models, 'validate_volume_size')
    def test_get_required_volume_size(self, vol_size_validator_mock):
        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 1.5},
                          {'flavor_id': 1, 'volume_size': 3}]
        total_size = models.get_required_volume_size(test_instances, True)
        self.assertEqual(14.5, total_size)
        vol_size_validator_mock.assert_has_calls([call(10),
                                                  call(1.5),
                                                  call(3)], any_order=True)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 1.5},
                          {'flavor_id': 1, 'volume_size': None}]
        self.assertRaises(exception.ClusterVolumeSizeRequired,
                          models.get_required_volume_size,
                          test_instances, True)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 1.5},
                          {'flavor_id': 1}]
        self.assertRaises(exception.ClusterVolumeSizeRequired,
                          models.get_required_volume_size,
                          test_instances, True)

        test_instances = [{'flavor_id': 1},
                          {'flavor_id': 1},
                          {'flavor_id': 1}]
        total_size = models.get_required_volume_size(test_instances, False)
        self.assertIsNone(total_size)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 1.5}]
        self.assertRaises(exception.VolumeNotSupported,
                          models.get_required_volume_size,
                          test_instances, False)

    def test_assert_same_instance_volumes(self):
        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        models.assert_same_instance_volumes(test_instances)

        test_instances = [{'flavor_id': 1, 'volume_size': 5},
                          {'flavor_id': 1, 'volume_size': 5},
                          {'flavor_id': 1, 'volume_size': 5}]
        models.assert_same_instance_volumes(test_instances, required_size=5)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 1.5},
                          {'flavor_id': 1, 'volume_size': 10}]
        self.assertRaises(exception.ClusterVolumeSizesNotEqual,
                          models.assert_same_instance_volumes,
                          test_instances)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        self.assertRaises(exception.ClusterVolumeSizesNotEqual,
                          models.assert_same_instance_volumes,
                          test_instances, required_size=5)

    def test_assert_same_instance_flavors(self):
        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        models.assert_same_instance_flavors(test_instances)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        models.assert_same_instance_flavors(test_instances, required_flavor=1)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 2, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        self.assertRaises(exception.ClusterFlavorsNotEqual,
                          models.assert_same_instance_flavors,
                          test_instances)

        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        self.assertRaises(exception.ClusterFlavorsNotEqual,
                          models.assert_same_instance_flavors,
                          test_instances, required_flavor=2)

    @patch.multiple(models, assert_same_instance_flavors=DEFAULT,
                    assert_same_instance_volumes=DEFAULT)
    def test_assert_homogeneous_cluster(self, assert_same_instance_flavors,
                                        assert_same_instance_volumes):
        test_instances = [{'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10},
                          {'flavor_id': 1, 'volume_size': 10}]
        required_flavor = Mock()
        required_volume_size = Mock()
        models.assert_homogeneous_cluster(
            test_instances, required_flavor=required_flavor,
            required_volume_size=required_volume_size)
        assert_same_instance_flavors.assert_called_once_with(
            test_instances, required_flavor=required_flavor)
        assert_same_instance_volumes.assert_called_once_with(
            test_instances, required_size=required_volume_size)
