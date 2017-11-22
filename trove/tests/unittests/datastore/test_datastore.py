# Copyright 2014 Rackspace
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

from mock import Mock
from mock import patch

from trove.common import exception
from trove.datastore import models as datastore_models
from trove.datastore.models import Datastore
from trove.tests.unittests.datastore.base import TestDatastoreBase


class TestDatastore(TestDatastoreBase):

    def test_create_failure_with_datastore_default_not_defined(self):
        self.assertRaises(
            exception.DatastoreDefaultDatastoreNotDefined,
            datastore_models.get_datastore_version)

    def test_load_datastore(self):
        datastore = Datastore.load(self.ds_name)
        self.assertEqual(self.ds_name, datastore.name)

    @patch.object(datastore_models, 'CONF')
    def test_create_failure_with_datastore_default(self, mock_conf):
        mock_conf.default_datastore = 'bad_ds'
        self.assertRaisesRegex(exception.DatastoreDefaultDatastoreNotFound,
                               "Default datastore 'bad_ds' cannot be found",
                               datastore_models.get_datastore_version)
        self.assertRaisesRegex(exception.DatastoreNotFound,
                               "Datastore 'my_ds' cannot be found",
                               datastore_models.get_datastore_version,
                               'my_ds')

    def test_get_datastore_or_version(self):
        # datastore, datastore_version, valid, exception
        data = [
            [None, None, True],
            ['ds', None, True],
            ['ds', 'ds_ver', True],
            [None, 'ds_ver', False, exception.DatastoreNoVersion],
        ]
        for datum in data:
            ds_id = datum[0]
            ds_ver_id = datum[1]
            valid = datum[2]
            expected_exception = None
            if not valid:
                expected_exception = datum[3]
            ds = Mock()
            ds.id = ds_id
            ds.name = ds_id
            ds_ver = Mock()
            ds_ver.id = ds_ver_id
            ds_ver.name = ds_ver_id
            ds_ver.datastore_id = ds_id
            with patch.object(datastore_models.Datastore, 'load',
                              return_value=ds):
                with patch.object(datastore_models.DatastoreVersion, 'load',
                                  return_value=ds_ver):
                    if valid:
                        (get_ds_id, get_ds_ver_id) = (
                            datastore_models.get_datastore_or_version(
                                ds_id, ds_ver_id))
                        self.assertEqual(ds_id, get_ds_id)
                        self.assertEqual(ds_ver_id, get_ds_ver_id)
                    else:
                        self.assertRaises(
                            expected_exception,
                            datastore_models.get_datastore_or_version,
                            ds_id, ds_ver_id)
