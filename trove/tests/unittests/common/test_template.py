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

from mock import Mock

from trove.common import exception
from trove.common import template
from trove.common import utils
from trove.datastore.models import DatastoreVersion
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TemplateTest(trove_testtools.TestCase):
    def setUp(self):
        super(TemplateTest, self).setUp()
        util.init_db()
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
        # expected query_cache_size = {{ 8 * flavor_multiplier }}M
        flavor_multiplier = test_flavor['ram'] // 512
        found_group = self._find_in_template(contents, teststr)
        if not found_group:
            raise "Could not find text in template"
        # Check that the last group has been rendered
        memsize = found_group.split(" ")[2]
        self.assertEqual("%sM" % (8 * flavor_multiplier), memsize)
        self.assertIsNotNone(server_id)
        self.assertGreater(len(server_id), 1)

    def test_rendering(self):
        rendered = self.template.render(flavor=self.flavor_dict,
                                        server_id=self.server_id)
        self.validate_template(rendered,
                               "query_cache_size",
                               self.flavor_dict,
                               self.server_id)

    def test_single_instance_config_rendering(self):
        datastore = Mock(spec=DatastoreVersion)
        datastore.datastore_name = 'MySql'
        datastore.name = 'mysql-5.6'
        datastore.manager = 'mysql'
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.validate_template(config.render(), "query_cache_size",
                               self.flavor_dict, self.server_id)

    def test_renderer_discovers_special_config(self):
        """Finds our special config file for the version 'mysql-test'."""
        datastore = Mock(spec=DatastoreVersion)
        datastore.datastore_name = 'mysql'
        datastore.name = 'mysql-test'
        datastore.manager = 'mysql'
        config = template.SingleInstanceConfigTemplate(datastore,
                                                       self.flavor_dict,
                                                       self.server_id)
        self.validate_template(config.render(), "hyper",
                               {'ram': 0}, self.server_id)

    def test_replica_source_config_rendering(self):
        datastore = Mock(spec=DatastoreVersion)
        datastore.datastore_name = 'MySql'
        datastore.name = 'mysql-5.6'
        datastore.manager = 'mysql'
        config = template.ReplicaSourceConfigTemplate(datastore,
                                                      self.flavor_dict,
                                                      self.server_id)
        self.assertTrue(self._find_in_template(config.render(), "log_bin"))

    def test_replica_config_rendering(self):
        datastore = Mock(spec=DatastoreVersion)
        datastore.datastore_name = 'MySql'
        datastore.name = 'mysql-5.6'
        datastore.manager = 'mysql'
        config = template.ReplicaConfigTemplate(datastore,
                                                self.flavor_dict,
                                                self.server_id)
        self.assertTrue(self._find_in_template(config.render(), "relay_log"))


class HeatTemplateLoadTest(trove_testtools.TestCase):

    class FakeTemplate():
        def __init__(self):
            self.name = 'mysql/heat.template'

    def setUp(self):
        self.default = 'default.heat.template'
        self.orig_1 = utils.ENV.list_templates
        self.orig_2 = utils.ENV.get_template
        super(HeatTemplateLoadTest, self).setUp()

    def tearDown(self):
        utils.ENV.list_templates = self.orig_1
        utils.ENV.get_template = self.orig_2
        super(HeatTemplateLoadTest, self).tearDown()

    def test_heat_template_load_with_invalid_datastore(self):
        invalid_datastore = 'mysql-blah'
        self.assertRaises(exception.InvalidDatastoreManager,
                          template.load_heat_template,
                          invalid_datastore)

    def test_heat_template_load_non_default(self):
        orig = utils.ENV._load_template
        utils.ENV._load_template = Mock(return_value=self.FakeTemplate())
        mysql_tmpl = template.load_heat_template('mysql')
        self.assertNotEqual(mysql_tmpl.name, self.default)
        utils.ENV._load_template = orig

    def test_heat_template_load_success(self):
        mysql_tmpl = template.load_heat_template('mysql')
        redis_tmpl = template.load_heat_template('redis')
        cassandra_tmpl = template.load_heat_template('cassandra')
        mongo_tmpl = template.load_heat_template('mongodb')
        percona_tmpl = template.load_heat_template('percona')
        couchbase_tmpl = template.load_heat_template('couchbase')
        self.assertIsNotNone(mysql_tmpl)
        self.assertIsNotNone(redis_tmpl)
        self.assertIsNotNone(cassandra_tmpl)
        self.assertIsNotNone(mongo_tmpl)
        self.assertIsNotNone(percona_tmpl)
        self.assertIsNotNone(couchbase_tmpl)
        self.assertEqual(self.default, mysql_tmpl.name)
        self.assertEqual(self.default, redis_tmpl.name)
        self.assertEqual(self.default, cassandra_tmpl.name)
        self.assertEqual(self.default, mongo_tmpl.name)
        self.assertEqual(self.default, percona_tmpl.name)
        self.assertEqual(self.default, couchbase_tmpl.name)

    def test_render_templates_with_ports_from_config(self):
        mysql_tmpl = template.load_heat_template('mysql')
        tcp_rules = [{'cidr': "0.0.0.0/0",
                      'from_': 3306,
                      'to_': 3309},
                     {'cidr': "0.0.0.0/0",
                      'from_': 3320,
                      'to_': 33022}]
        output = mysql_tmpl.render(
            volume_support=True,
            ifaces=[], ports=[],
            tcp_rules=tcp_rules,
            udp_rules=[],
            files={})
        self.assertIsNotNone(output)
        self.assertIn('FromPort: "3306"', output)
        self.assertIn('ToPort: "3309"', output)
        self.assertIn('CidrIp: "0.0.0.0/0"', output)
        self.assertIn('FromPort: "3320"', output)
        self.assertIn('ToPort: "33022"', output)

    def test_no_rules_if_no_ports(self):
        mysql_tmpl = template.load_heat_template('mysql')
        output = mysql_tmpl.render(
            volume_support=True,
            ifaces=[], ports=[],
            tcp_rules=[],
            udp_rules=[],
            files={})
        self.assertIsNotNone(output)
        self.assertNotIn('- IpProtocol: "tcp"', output)
        self.assertNotIn('- IpProtocol: "udp"', output)
