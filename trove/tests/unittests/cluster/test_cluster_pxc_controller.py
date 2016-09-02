# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import jsonschema

from mock import MagicMock
from mock import Mock
from mock import patch
from testtools.matchers import Is, Equals
from trove.cluster import models
from trove.cluster.models import Cluster
from trove.cluster.service import ClusterController
from trove.cluster import views
import trove.common.cfg as cfg
from trove.common import exception
from trove.common import utils
from trove.datastore import models as datastore_models
from trove.tests.unittests import trove_testtools


class TestClusterController(trove_testtools.TestCase):
    def setUp(self):
        super(TestClusterController, self).setUp()
        self.controller = ClusterController()
        instances = [
            {
                "flavorRef": "7",
                "volume": {
                    "size": 1
                },
                "availability_zone": "az",
                "nics": [
                    {"net-id": "e89aa5fd-6b0a-436d-a75c-1545d34d5331"}
                ]
            }
        ] * 3

        self.cluster = {
            "cluster": {
                "name": "products",
                "datastore": {
                    "type": "pxc",
                    "version": "5.5"
                },
                "instances": instances
            }
        }

    def test_get_schema_create(self):
        schema = self.controller.get_schema('create', self.cluster)
        self.assertIsNotNone(schema)
        self.assertIn('cluster', schema['properties'])
        self.assertTrue('cluster')

    def test_validate_create(self):
        body = self.cluster
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_blankname(self):
        body = self.cluster
        body['cluster']['name'] = "     "
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'     ' does not match '^.*[0-9a-zA-Z]+.*$'"))

    def test_validate_create_blank_datastore(self):
        body = self.cluster
        body['cluster']['datastore']['type'] = ""
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        error_paths = [error.path.pop() for error in errors]
        self.assertThat(len(errors), Is(2))
        self.assertIn("'' is too short", error_messages)
        self.assertIn("'' does not match '^.*[0-9a-zA-Z]+.*$'", error_messages)
        self.assertIn("type", error_paths)

    @patch.object(Cluster, 'create')
    @patch.object(datastore_models, 'get_datastore_version')
    def test_create_clusters_disabled(self,
                                      mock_get_datastore_version,
                                      mock_cluster_create):
        body = self.cluster
        tenant_id = Mock()
        context = trove_testtools.TroveTestContext(self)

        req = Mock()
        req.environ = MagicMock()
        req.environ.get = Mock(return_value=context)

        datastore_version = Mock()
        datastore_version.manager = 'mysql'
        mock_get_datastore_version.return_value = (Mock(), datastore_version)

        self.assertRaises(exception.ClusterDatastoreNotSupported,
                          self.controller.create,
                          req,
                          body,
                          tenant_id)

    @patch.object(Cluster, 'create')
    @patch.object(utils, 'get_id_from_href')
    @patch.object(datastore_models, 'get_datastore_version')
    def test_create_clusters(self,
                             mock_get_datastore_version,
                             mock_id_from_href,
                             mock_cluster_create):
        body = self.cluster
        tenant_id = Mock()
        context = trove_testtools.TroveTestContext(self)

        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        datastore_version = Mock()
        datastore_version.manager = 'pxc'
        datastore = Mock()
        mock_get_datastore_version.return_value = (datastore,
                                                   datastore_version)
        instances = [
            {
                'volume_size': 1,
                'volume_type': None,
                'flavor_id': '1234',
                'availability_zone': 'az',
                'nics': [
                    {'net-id': 'e89aa5fd-6b0a-436d-a75c-1545d34d5331'}
                ]
            }
        ] * 3
        mock_id_from_href.return_value = '1234'

        mock_cluster = Mock()
        mock_cluster.instances = []
        mock_cluster.instances_without_server = []
        mock_cluster.datastore_version.manager = 'pxc'
        mock_cluster_create.return_value = mock_cluster

        self.controller.create(req, body, tenant_id)
        mock_cluster_create.assert_called_with(context, 'products',
                                               datastore, datastore_version,
                                               instances, {}, None)

    @patch.object(Cluster, 'load')
    def test_show_cluster(self,
                          mock_cluster_load):
        tenant_id = Mock()
        id = Mock()
        context = trove_testtools.TroveTestContext(self)
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)

        mock_cluster = Mock()
        mock_cluster.instances = []
        mock_cluster.instances_without_server = []
        mock_cluster.datastore_version.manager = 'pxc'
        mock_cluster_load.return_value = mock_cluster

        self.controller.show(req, tenant_id, id)
        mock_cluster_load.assert_called_with(context, id)

    @patch.object(Cluster, 'load')
    @patch.object(Cluster, 'load_instance')
    def test_show_cluster_instance(self,
                                   mock_cluster_load_instance,
                                   mock_cluster_load):
        tenant_id = Mock()
        cluster_id = Mock()
        instance_id = Mock()
        context = trove_testtools.TroveTestContext(self)
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        cluster = Mock()
        mock_cluster_load.return_value = cluster
        cluster.id = cluster_id
        self.controller.show_instance(req, tenant_id, cluster_id, instance_id)
        mock_cluster_load_instance.assert_called_with(context, cluster.id,
                                                      instance_id)

    @patch.object(Cluster, 'load')
    def test_delete_cluster(self, mock_cluster_load):
        tenant_id = Mock()
        cluster_id = Mock()
        req = MagicMock()
        cluster = Mock()
        trove_testtools.patch_notifier(self)
        mock_cluster_load.return_value = cluster
        self.controller.delete(req, tenant_id, cluster_id)
        cluster.delete.assert_called_with()


class TestClusterControllerWithStrategy(trove_testtools.TestCase):
    def setUp(self):
        super(TestClusterControllerWithStrategy, self).setUp()
        self.controller = ClusterController()
        self.cluster = {
            "cluster": {
                "name": "products",
                "datastore": {
                    "type": "pxc",
                    "version": "5.5"
                },
                "instances": [
                    {
                        "flavorRef": "7",
                        "volume": {
                            "size": 1
                        },
                    },
                    {
                        "flavorRef": "7",
                        "volume": {
                            "size": 1
                        },
                    },
                    {
                        "flavorRef": "7",
                        "volume": {
                            "size": 1
                        },
                    },
                ]
            }
        }

    def tearDown(self):
        super(TestClusterControllerWithStrategy, self).tearDown()
        cfg.CONF.clear_override('cluster_support', group='pxc')
        cfg.CONF.clear_override('api_strategy', group='pxc')

    @patch.object(datastore_models, 'get_datastore_version')
    @patch.object(models.Cluster, 'create')
    def test_create_clusters_disabled(self,
                                      mock_cluster_create,
                                      mock_get_datastore_version):

        cfg.CONF.set_override('cluster_support', False, group='pxc',
                              enforce_type=True)

        body = self.cluster
        tenant_id = Mock()
        context = trove_testtools.TroveTestContext(self)

        req = Mock()
        req.environ = MagicMock()
        req.environ.get = Mock(return_value=context)

        datastore_version = Mock()
        datastore_version.manager = 'pxc'
        mock_get_datastore_version.return_value = (Mock(), datastore_version)

        self.assertRaises(exception.TroveError, self.controller.create, req,
                          body, tenant_id)

    @patch.object(views.ClusterView, 'data', return_value={})
    @patch.object(datastore_models, 'get_datastore_version')
    @patch.object(models.Cluster, 'create')
    def test_create_clusters_enabled(self,
                                     mock_cluster_create,
                                     mock_get_datastore_version,
                                     mock_cluster_view_data):

        cfg.CONF.set_override('cluster_support', True, group='pxc',
                              enforce_type=True)

        body = self.cluster
        tenant_id = Mock()
        context = trove_testtools.TroveTestContext(self)

        req = Mock()
        req.environ = MagicMock()
        req.environ.get = Mock(return_value=context)

        datastore_version = Mock()
        datastore_version.manager = 'pxc'
        mock_get_datastore_version.return_value = (Mock(), datastore_version)

        mock_cluster = Mock()
        mock_cluster.datastore_version.manager = 'pxc'
        mock_cluster_create.return_value = mock_cluster
        self.controller.create(req, body, tenant_id)
