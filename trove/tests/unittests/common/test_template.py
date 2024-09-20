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
import re

from unittest.mock import Mock
from unittest.mock import patch

from semantic_version import Version

from trove.common import template
from trove.common.utils import ENV
from trove.datastore.models import DatastoreVersion
from trove.tests.unittests import trove_testtools


def mock_datastore_version(datastore_name='MySQL', name='mysql-5.7',
                           manager='mysql', version=''):
    datastore = Mock(spec=DatastoreVersion)
    datastore.datastore_name = datastore_name
    datastore.name = name
    datastore.manager = manager
    datastore.version = version
    return datastore


class TemplateTest(trove_testtools.TestCase):
    def setUp(self):
        super(TemplateTest, self).setUp()
        self.env = template.ENV
        self.template = self.env.get_template("mysql/config.template")
        self.flavor_dict = {'ram': 1024, 'name': 'small', 'id': '55'}
        self.server_id = "180b5ed1-3e57-4459-b7a3-2aeee4ac012a"

    def tearDown(self):
        super(TemplateTest, self).tearDown()

    def _find_in_template(self, contents, teststr):
        found_group = None
        for line in contents.split('\n'):
            m = re.search('^%s.*' % teststr, line)
            if m:
                found_group = m.group(0)
        return found_group

    def validate_template(self, contents, teststr, test_flavor, server_id):
        # expected innodb_buffer_pool_size = {{ (150 * flavor_multiplier }}M
        flavor_multiplier = test_flavor['ram'] // 512
        found_group = self._find_in_template(contents, teststr)
        if not found_group:
            raise Exception("Could not find text in template")
        # Check that the last group has been rendered
        memsize = found_group.split(" ")[2]
        self.assertEqual("%sM" % (150 * flavor_multiplier), memsize)
        self.assertIsNotNone(server_id)
        self.assertGreater(len(server_id), 1)

    def test_rendering(self):
        rendered = self.template.render(flavor=self.flavor_dict,
                                        server_id=self.server_id)
        self.validate_template(rendered,
                               "innodb_buffer_pool_size",
                               self.flavor_dict,
                               self.server_id)

    def test_single_instance_config_rendering(self):
        datastore = mock_datastore_version()
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.validate_template(config.render(), "innodb_buffer_pool_size",
                               self.flavor_dict, self.server_id)

    def test_renderer_discovers_special_config(self):
        """Finds our special config file for the version 'mysql-test'."""
        datastore = mock_datastore_version(name='mysql-test',
                                           manager='mysql',
                                           datastore_name='mysql')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.validate_template(config.render(), "hyper",
                               {'ram': 0}, self.server_id)

    def test_replica_source_config_rendering(self):
        datastore = mock_datastore_version()
        config = template.ReplicaSourceConfigTemplate(datastore,
                                                      self.flavor_dict,
                                                      self.server_id)
        self.assertTrue(self._find_in_template(config.render(), "log_bin"))

    def test_replica_config_rendering(self):
        datastore = mock_datastore_version()
        config = template.ReplicaConfigTemplate(datastore,
                                                self.flavor_dict,
                                                self.server_id)
        self.assertTrue(self._find_in_template(config.render(), "relay_log"))

    def test_replica_config_rendering_mysql_v8(self):
        datastore = mock_datastore_version(name='8.0')
        config = template.ReplicaConfigTemplate(datastore,
                                                self.flavor_dict,
                                                self.server_id)
        self.assertTrue(self._find_in_template(config.render(),
                                               "binlog_format"))

    def test_config_postgresql_pre_v13_sets_wal_keep_segments(self):
        datastore = mock_datastore_version(datastore_name='PostgreSQL',
                                           name='12.17',
                                           manager='postgresql')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.assertTrue(
            self._find_in_template(config.render(), "wal_keep_segments"))
        self.assertIsNone(
            self._find_in_template(config.render(), "wal_keep_size"))

    def test_config_postgresql_post_v12_sets_wal_keep_size(self):
        datastore = mock_datastore_version(datastore_name='PostgreSQL',
                                           name='13.2',
                                           manager='postgresql')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.assertTrue(
            self._find_in_template(config.render(), "wal_keep_size"))
        self.assertIsNone(
            self._find_in_template(config.render(), "wal_keep_segments"))

    def test_parse_version_name_missing_release_number(self):
        datastore = mock_datastore_version(datastore_name='PostgreSQL',
                                           name='test',
                                           manager='postgresql')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.assertEqual(Version(major=0, minor=0, patch=0),
                         config._parse_datastore_version())

    def test_parse_version_release_part_of_name(self):
        datastore = mock_datastore_version(datastore_name='PostgreSQL',
                                           name='test-12.17',
                                           manager='postgresql')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.assertEqual(Version(major=0, minor=0, patch=0),
                         config._parse_datastore_version())

    def test_parse_version_name_with_prefix(self):
        datastore = mock_datastore_version(datastore_name='PostgreSQL',
                                           name='16.1-test',
                                           manager='postgresql')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.assertEqual(Version(major=16, minor=1, patch=0,
                                 prerelease=('test',)),
                         config._parse_datastore_version())

    def test_parse_version_prefer_version_if_set(self):
        datastore = mock_datastore_version(datastore_name='PostgreSQL',
                                           name='test',
                                           manager='postgresql',
                                           version='16.1')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.assertEqual(Version(major=16, minor=1, patch=0,
                                 ),
                         config._parse_datastore_version())

    def test_template_paths(self):
        datastore = mock_datastore_version(name='5.7.9')
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        with patch.object(ENV, 'select_template') as select_template_mock:
            config.get_template()
            select_template_mock.assert_called_with(
                ['MySQL/5.7.9/config.template',
                 'MySQL/5.7/config.template',
                 'MySQL/5/config.template',
                 'MySQL/config.template',
                 'mysql/config.template'
                 ]
            )
