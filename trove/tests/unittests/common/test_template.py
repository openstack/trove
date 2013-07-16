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
from trove.tests.unittests.util import util


class TemplateTest(testtools.TestCase):
    def setUp(self):
        super(TemplateTest, self).setUp()
        util.init_db()
        self.env = template.get_env()
        self.template = self.env.get_template("mysql.config.template")
        self.flavor_dict = {'ram': 1024}

    def tearDown(self):
        super(TemplateTest, self).tearDown()

    def validate_template(self, contents, teststr, test_flavor):
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

    def test_rendering(self):
        rendered = self.template.render(flavor=self.flavor_dict)
        self.validate_template(rendered, "query_cache_size", self.flavor_dict)

    def test_single_instance_config_rendering(self):
        location = "/etc/mysql/my.cnf"
        config = template.SingleInstanceConfigTemplate('mysql',
                                                       self.flavor_dict)
        config.render()
        self.assertEqual(location, config.config_location)
        self.validate_template(config.config_contents, "query_cache_size",
                               self.flavor_dict)
