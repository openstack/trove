# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#
from unittest.mock import Mock, patch

from oslo_config import cfg
from oslo_middleware import http_proxy_to_wsgi
from testtools.matchers import Equals, Is, Not
import webob.exc

from trove.common import base_wsgi
from trove.common import exception
from trove.common import pagination
from trove.common import views
from trove.common import wsgi
from trove.tests.unittests import trove_testtools
import webob


class TestWsgi(trove_testtools.TestCase):
    def test_process_request(self):
        middleware = wsgi.ContextMiddleware("test_trove")
        req = webob.BaseRequest({})
        token = 'MI23fdf2defg123'
        user_id = 'test_user_id'
        req.headers = {
            'X-User': 'do not use - deprecated',
            'X-User-ID': user_id,
            'X-Auth-Token': token,
            'X-Service-Catalog': '[]'
        }
        req.environ = {}
        # invocation
        middleware.process_request(req)
        # assertions
        ctx = req.environ[wsgi.CONTEXT_KEY]
        self.assertThat(ctx, Not(Is(None)))
        self.assertThat(ctx.user_id, Equals(user_id))
        self.assertThat(ctx.auth_token, Equals(token))
        self.assertEqual(0, len(ctx.service_catalog))


class TestProxyLinks(trove_testtools.TestCase):

    def test_links_use_forwarded_https_scheme(self):
        conf = cfg.ConfigOpts()
        middleware = http_proxy_to_wsgi.HTTPProxyToWSGI(None, conf=conf)
        conf.set_override('enable_proxy_headers_parsing', True,
                          group='oslo_middleware')
        proxy_headers = (
            {'X-Forwarded-Proto': 'https',
             'X-Forwarded-Host': 'public.example.com'},
            {'Forwarded': 'proto=https;host=public.example.com'},
        )
        for headers in proxy_headers:
            with self.subTest(headers=headers):
                req = wsgi.Request.blank(
                    'http://backend:8779/v1.0/project/instances?limit=1',
                    headers=headers)
                req.environ[wsgi.CONTEXT_KEY] = Mock(project_id='project')

                middleware.process_request(req)

                self.assertEqual(
                    [{'rel': 'self',
                      'href': 'https://public.example.com/v1.0/project/'
                      'instances/instance-id'},
                     {'rel': 'bookmark',
                      'href': 'https://public.example.com/'
                      'instances/instance-id'}],
                    views.create_links('instances', req, 'instance-id'))
                expected_next_links = [
                    {'rel': 'next',
                     'href': 'https://public.example.com/v1.0/project/'
                     'instances?limit=1&marker=next-marker'}]
                paged = pagination.PaginatedDataView(
                    'instances', [], req.url, next_page_marker='next-marker')
                self.assertEqual(expected_next_links, paged._links())
                view = Mock()
                view.data.return_value = {'instances': []}
                simple_paged = pagination.SimplePaginatedDataView(
                    req.url, 'instances', view, 'next-marker')
                self.assertEqual(expected_next_links,
                                 simple_paged.data()['links'])


class TestController(trove_testtools.TestCase):

    @patch.object(base_wsgi.Resource, 'execute_action',
                  side_effect=exception.RootHistoryNotFound())
    @patch.object(wsgi.Controller, 'delete', create=True)
    @patch.object(wsgi.Controller, 'validate_request')
    def test_exception_root_history_notfound(self, *args):
        controller = wsgi.Controller()
        resource = controller.create_resource()
        req = Mock()
        result = resource.execute_action('delete', req)
        self.assertIsInstance(result.wrapped_exc,
                              webob.exc.HTTPNotFound)
