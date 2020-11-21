# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from unittest import mock

from trove.common import cfg
from trove.common import wsgi
from trove.configuration import models as config_models
from trove.configuration import service
from trove.datastore import models as ds_models
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util

CONF = cfg.CONF


class TestConfigurationsController(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()

        cls.ds_name = cls.random_name(
            'datastore', prefix='TestConfigurationsController')
        ds_models.update_datastore(name=cls.ds_name, default_version=None)
        cls.ds = ds_models.Datastore.load(cls.ds_name)

        ds_version_name = cls.random_name(
            'version', prefix='TestConfigurationsController')
        ds_models.update_datastore_version(
            cls.ds_name, ds_version_name, 'mysql', '',
            ['trove'], '', 1, version='5.7.29')
        cls.ds_version = ds_models.DatastoreVersion.load(
            cls.ds, ds_version_name, version='5.7.29')

        cls.tenant_id = cls.random_uuid()
        cls.config = config_models.Configuration.create(
            cls.random_name('configuration'),
            '', cls.tenant_id, None,
            cls.ds_version.id)
        cls.config_id = cls.config.id

        cls.controller = service.ConfigurationsController()

        super(TestConfigurationsController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()

        super(TestConfigurationsController, cls).tearDownClass()

    def test_show(self):
        req_mock = mock.MagicMock(
            environ={
                wsgi.CONTEXT_KEY: mock.MagicMock(project_id=self.tenant_id)
            }
        )
        result = self.controller.show(req_mock, self.tenant_id,
                                      self.config_id)
        data = result.data(None).get('configuration')

        expected = {
            "id": self.config_id,
            "name": self.config.name,
            "description": '',
            "instance_count": 0,
            "datastore_name": self.ds_name,
            "datastore_version_id": self.ds_version.id,
            "datastore_version_name": self.ds_version.name,
            "datastore_version_number": self.ds_version.version
        }

        self.assertDictContains(data, expected)
