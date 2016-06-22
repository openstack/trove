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
        self.assertRaisesRegexp(exception.DatastoreDefaultDatastoreNotFound,
                                "Default datastore 'bad_ds' cannot be found",
                                datastore_models.get_datastore_version)
        self.assertRaisesRegexp(exception.DatastoreNotFound,
                                "Datastore 'my_ds' cannot be found",
                                datastore_models.get_datastore_version,
                                'my_ds')
