# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
""" Taken from melange. """
import routes
import webob
import webob.exc
import webtest

from reddwarf.common import wsgi
from reddwarf import tests


class StubApp(object):

    def __init__(self):
        self.called = False

    def __call__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        self.called = True


class StubUrlMap(StubApp, dict):

    def __init__(self, dictionary):
        self.update(dictionary)
        super(StubUrlMap, self).__init__()


class VersionedURLMapTest(tests.BaseTest):

    def setUp(self):
        self.v1_app = StubApp()
        self.v2_app = StubApp()
        self.root_app = StubApp()
        self.urlmap = StubUrlMap({'/v2.0': self.v2_app,
                                  '/v1.0': self.v1_app,
                                  '/': self.root_app})
        self.versioned_urlmap = wsgi.VersionedURLMap(self.urlmap)
        super(VersionedURLMapTest, self).setUp()

    def test_chooses_app_based_on_accept_version(self):
        environ = {'HTTP_ACCEPT': "application/vnd.openstack.reddwarf+xml;"
                   "version=1.0",
                   'PATH_INFO': "/resource"}
        self.versioned_urlmap(environ=environ, start_response=None)

        self.assertTrue(self.v1_app.called)

    def test_delegates_to_urlmapper_when_accept_header_is_absent(self):
        self.versioned_urlmap(environ={'PATH_INFO': "/resource"},
                              start_response=None)

        self.assertTrue(self.urlmap.called)

    def test_delegates_to_urlmapper_for_std_accept_headers_with_version(self):
        environ = {
            'HTTP_ACCEPT': "application/json;version=1.0",
            'PATH_INFO': "/resource",
            }

        self.versioned_urlmap(environ=environ, start_response=None)

        self.assertTrue(self.urlmap.called)

    def test_delegates_to_urlmapper_for_nonexistant_version_of_app(self):
        environ = {
            'HTTP_ACCEPT': "application/vnd.openstack.reddwarf+xml;"
            "version=9.0", 'REQUEST_METHOD': "GET",
            'PATH_INFO': "/resource.xml",
            }

        def assert_status(status, *args):
            self.assertEqual(status, "406 Not Acceptable")

        self.versioned_urlmap(environ=environ, start_response=assert_status)

    def test_delegates_to_urlmapper_when_url_versioned(self):
        environ = {
            'HTTP_ACCEPT': "application/vnd.openstack.reddwarf+xml;"
            "version=2.0",
            'PATH_INFO': "/v1.0/resource",
            }

        self.versioned_urlmap(environ=environ, start_response=None)

        self.assertTrue(self.urlmap.called)


class RequestTest(tests.BaseTest):

    def test_content_type_from_accept_header(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/xml")

        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/json"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = "application/xml, application/json"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = \
            "application/json; q=0.3, application/xml; q=0.9"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/xml")

    def test_content_type_from_accept_header_with_versioned_mimetype(self):
        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = \
            "application/vnd.openstack.reddwarf+xml;version=66.0"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/xml")

        request = wsgi.Request.blank('/tests/123')
        request.headers["Accept"] = \
            "application/vnd.openstack.reddwarf+json;version=96.0"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_from_query_extension(self):
        request = wsgi.Request.blank('/tests/123.xml')
        result = request.best_match_content_type()
        self.assertEqual(result, "application/xml")

        request = wsgi.Request.blank('/tests/123.json')
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

        request = wsgi.Request.blank('/tests/123.invalid')
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_content_type_accept_and_query_extension(self):
        request = wsgi.Request.blank('/tests/123.xml')
        request.headers["Accept"] = "application/json"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/xml")

    def test_content_type_accept_default(self):
        request = wsgi.Request.blank('/tests/123.unsupported')
        request.headers["Accept"] = "application/unsupported1"
        result = request.best_match_content_type()
        self.assertEqual(result, "application/json")

    def test_accept_version_for_custom_mime_type(self):
        environ = {'HTTP_ACCEPT': "application/vnd.openstack.reddwarf+xml;"
                   "version=1.0"}
        request = wsgi.Request(environ=environ)

        self.assertEqual(request.accept_version, "1.0")

    def test_accept_version_from_first_custom_mime_type(self):
        environ = {'HTTP_ACCEPT': "application/json;version=2.0, "
                   "application/vnd.openstack.reddwarf+xml;version=1.0, "
                   "application/vnd.openstack.reddwarf+json;version=4.0"}
        request = wsgi.Request(environ=environ)

        self.assertEqual(request.accept_version, "1.0")

    def test_accept_version_is_none_for_standard_mime_type(self):
        environ = {'HTTP_ACCEPT': "application/json;"
                   "version=1.0"}
        request = wsgi.Request(environ=environ)

        self.assertIsNone(request.accept_version)

    def test_accept_version_is_none_for_invalid_mime_type(self):
        environ = {'HTTP_ACCEPT': "glibberish;"
                   "version=1.0"}
        request = wsgi.Request(environ=environ)

        self.assertIsNone(request.accept_version)

    def test_accept_version_none_when_mime_type_doesnt_specify_version(self):
        environ = {'HTTP_ACCEPT': "application/vnd.openstack.reddwarf+xml"}
        request = wsgi.Request(environ=environ)

        self.assertIsNone(request.accept_version)

    def test_accept_version_is_none_when_accept_header_is_absent(self):
        request = wsgi.Request(environ={})

        self.assertIsNone(request.accept_version)

    def test_accept_version_is_none_for_mime_type_with_invalid_version(self):
        environ = {'HTTP_ACCEPT': "application/vnd.openstack.reddwarf+xml;"
                   "version=foo.bar"}
        request = wsgi.Request(environ=environ)

        self.assertIsNone(request.accept_version)

    def test_url_version_for_versioned_url(self):
        request = wsgi.Request.blank("/v1.0/resource")

        self.assertEqual(request.url_version, "1.0")

    def test_url_version_for_non_versioned_url_is_none(self):
        request = wsgi.Request.blank("/resource")

        self.assertIsNone(request.url_version)

    def test_request_params_returns_non_unicode_strings(self):
        request = wsgi.Request.blank("/resource?x=y&a=b")
        for key in request.params:
            self.assertEqual(type(key), str)


class DummyApp(wsgi.Router):

    def __init__(self):
        mapper = routes.Mapper()
        controller = StubController()
        mapper.resource("resource", "/resources",
                        controller=controller.create_resource())
        super(DummyApp, self).__init__(mapper)


class StubController(wsgi.Controller):

    def index(self, request, format=None):
        return  {'fort': 'knox'}


class TestController(tests.BaseTest):

    def test_response_content_type_matches_accept_header(self):
        app = webtest.TestApp(DummyApp())

        response = app.get("/resources", headers={'Accept': "application/xml"})

        self.assertEqual(response.content_type, "application/xml")
        self.assertEqual(response.xml.tag, "fort")
        self.assertEqual(response.xml.text.strip(), "knox")

    def test_response_content_type_matches_url_format_over_accept_header(self):
        app = webtest.TestApp(DummyApp())

        response = app.get("/resources.json",
                           headers={'Accept': "application/xml"})

        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.json, {'fort': 'knox'})

    def test_returns_404_if_action_not_implemented(self):
        app = webtest.TestApp(DummyApp())

        response = app.get("/resources/new", status='*')

        self.assertEqual(response.status_int, 404)


class TestFault(tests.BaseTest):

    def test_fault_wraps_webob_exception(self):
        app = webtest.TestApp(wsgi.Fault(webob.exc.HTTPNotFound("some error")))
        response = app.get("/", status="*")
        self.assertEqual(response.status_int, 404)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.json['NotFound'],
                         dict(code=404,
                              message="The resource could not be found.",
                              detail="some error"))

    def test_fault_gives_back_xml(self):
        app = webtest.TestApp(wsgi.Fault(
            webob.exc.HTTPBadRequest("some error")))
        response = app.get("/x.xml", status="*")
        self.assertEqual(response.content_type, "application/xml")
        self.assertEqual(response.xml.tag, 'BadRequest')
        self.assertEqual(response.xml.attrib['code'], '400')
        self.assertEqual(response.xml.find('detail').text.strip(),
                         'some error')


class TestResult(tests.BaseTest):

    class TestData(object):

        def data_for_json(self):
            return {'foo': "bar", 'foo2': "bar2"}

        def data_for_xml(self):
            return {'foos': [{'foo': "bar"}, {'foo2': "bar2"}]}

    def test_data_returns_back_input_data(self):
        self.assertEqual(wsgi.Result("blah").data("application/json"), "blah")
        self.assertEqual(wsgi.Result({'x': "blah"}).data("application/json"),
                         {'x': "blah"})
        self.assertEqual(wsgi.Result(["x", "blah"]).data("application/xml"),
                         ["x", "blah"])

    def test_data_returns_json_specific_input_data(self):
        self.assertEqual(wsgi.Result(self.TestData()).data("application/json"),
                         {'foo': "bar", 'foo2': "bar2"})

    def test_data_returns_xml_specific_input_data(self):
        self.assertEqual(wsgi.Result(self.TestData()).data("application/xml"),
                         {'foos': [{'foo': "bar"}, {'foo2': "bar2"}]})
