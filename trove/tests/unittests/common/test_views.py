# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from unittest.mock import Mock

from trove.common import views
from trove.common import wsgi
from trove.tests.unittests import trove_testtools


class TestCreateLinks(trove_testtools.TestCase):

    def test_preserves_request_scheme(self):
        for scheme in ('http', 'https'):
            for authority in ('example.com', 'example.com:8779'):
                with self.subTest(scheme=scheme, authority=authority):
                    base_url = '%s://%s' % (scheme, authority)
                    req = wsgi.Request.blank(
                        base_url + '/v1.0/project/datastores/versions',
                        headers={'Host': authority})
                    req.environ[wsgi.CONTEXT_KEY] = Mock(project_id='project')

                    self.assertEqual(
                        [{'rel': 'self',
                          'href': base_url + '/v1.0/project/'
                          'datastores/versions/version-id'},
                         {'rel': 'bookmark',
                          'href': base_url +
                          '/datastores/versions/version-id'}],
                        views.create_links(
                            'datastores/versions', req, 'version-id'))
