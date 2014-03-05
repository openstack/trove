#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.


import testtools
import re

from trove.common import template
from trove.common import exception
from trove.tests.unittests.util import util


class TemplateTest(testtools.TestCase):
    def setUp(self):
        super(TemplateTest, self).setUp()
        util.init_db()
        self.env = template.ENV
        self.template = self.env.get_template("mysql/config.template")
        self.flavor_dict = {'ram': 1024}
        self.server_id = "180b5ed1-3e57-4459-b7a3-2aeee4ac012a"

    def tearDown(self):
        super(TemplateTest, self).tearDown()

    def validate_template(self, contents, teststr, test_flavor, server_id):
        # expected query_cache_size = {{ 8 * flavor_multiplier }}M
        flavor_multiplier = test_flavor['ram'] / 512
        found_group = None
        for line in contents.split('\n'):
            m = re.search('^%s.*' % teststr, line)
            if m:
                found_group = m.group(0)
        if not found_group:
            raise "Could not find text in template"
        # Check that the last group has been rendered
        memsize = found_group.split(" ")[2]
        self.assertEqual(memsize, "%sM" % (8 * flavor_multiplier))
        self.assertIsNotNone(server_id)
        self.assertTrue(server_id > 1)

    def test_rendering(self):
        rendered = self.template.render(flavor=self.flavor_dict,
                                        server_id=self.server_id)
        self.validate_template(rendered,
                               "query_cache_size",
                               self.flavor_dict,
                               self.server_id)

    def test_single_instance_config_rendering(self):
        config = template.SingleInstanceConfigTemplate('mysql',
                                                       self.flavor_dict,
                                                       self.server_id)
        self.validate_template(config.render(), "query_cache_size",
                               self.flavor_dict, self.server_id)


class HeatTemplateLoadTest(testtools.TestCase):

    def setUp(self):
        super(HeatTemplateLoadTest, self).setUp()

    def tearDown(self):
        super(HeatTemplateLoadTest, self).tearDown()

    def test_heat_template_load_fail(self):
        self.assertRaises(exception.TroveError,
                          template.load_heat_template,
                          'mysql-blah')

    def test_heat_template_load_success(self):
        mysql_tmpl = template.load_heat_template('mysql')
        #TODO(denis_makogon): use it when redis template would be added
        #redis_tmplt = template.load_heat_template('redis')
        cassandra_tmpl = template.load_heat_template('cassandra')
        mongo_tmpl = template.load_heat_template('mongodb')
        self.assertIsNotNone(mysql_tmpl)
        self.assertIsNotNone(cassandra_tmpl)
        self.assertIsNotNone(mongo_tmpl)
        # self.assertIsNotNone(redis_tmpl)
