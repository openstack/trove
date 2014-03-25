# Copyright 2011 OpenStack Foundation
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

"""
Tests dealing with HTTP rate-limiting.
"""

import httplib
import StringIO
from trove.quota.models import Quota
import testtools
import webob

from mock import Mock, MagicMock
from trove.common import limits
from trove.common.limits import Limit
from trove.limits import views
from trove.limits.service import LimitsController
from trove.openstack.common import jsonutils
from trove.quota.quota import QUOTAS

TEST_LIMITS = [
    Limit("GET", "/delayed", "^/delayed", 1, limits.PER_MINUTE),
    Limit("POST", "*", ".*", 7, limits.PER_MINUTE),
    Limit("PUT", "*", "", 10, limits.PER_MINUTE),
]


class BaseLimitTestSuite(testtools.TestCase):
    """Base test suite which provides relevant stubs and time abstraction."""

    def setUp(self):
        super(BaseLimitTestSuite, self).setUp()
        self.absolute_limits = {"max_instances": 55,
                                "max_volumes": 100,
                                "max_backups": 40}


class LimitsControllerTest(BaseLimitTestSuite):
    def setUp(self):
        super(LimitsControllerTest, self).setUp()

    def test_limit_index_empty(self):
        limit_controller = LimitsController()

        req = MagicMock()
        req.environ = {}

        QUOTAS.get_all_quotas_by_tenant = MagicMock(return_value={})

        view = limit_controller.index(req, "test_tenant_id")
        expected = {'limits': [{'verb': 'ABSOLUTE'}]}
        self.assertEqual(expected, view._data)

    def test_limit_index(self):
        tenant_id = "test_tenant_id"
        limit_controller = LimitsController()

        limits = [
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "POST",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            },
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "PUT",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            },
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "DELETE",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            },
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "GET",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            }
        ]

        abs_limits = {"instances": Quota(tenant_id=tenant_id,
                                         resource="instances",
                                         hard_limit=100),

                      "backups": Quota(tenant_id=tenant_id,
                                       resource="backups",
                                       hard_limit=40),

                      "volumes": Quota(tenant_id=tenant_id,
                                       resource="volumes",
                                       hard_limit=55)}

        req = MagicMock()
        req.environ = {"trove.limits": limits}

        QUOTAS.get_all_quotas_by_tenant = MagicMock(return_value=abs_limits)

        view = limit_controller.index(req, tenant_id)

        expected = {
            'limits': [
                {
                    'max_instances': 100,
                    'max_backups': 40,
                    'verb': 'ABSOLUTE',
                    'max_volumes': 55
                },
                {
                    'regex': '.*',
                    'nextAvailable': '2011-07-21T18:17:06Z',
                    'uri': '*',
                    'value': 10,
                    'verb': 'POST',
                    'remaining': 2,
                    'unit': 'MINUTE'
                },
                {
                    'regex': '.*',
                    'nextAvailable': '2011-07-21T18:17:06Z',
                    'uri': '*',
                    'value': 10,
                    'verb': 'PUT',
                    'remaining': 2,
                    'unit': 'MINUTE'
                },
                {
                    'regex': '.*',
                    'nextAvailable': '2011-07-21T18:17:06Z',
                    'uri': '*',
                    'value': 10,
                    'verb': 'DELETE',
                    'remaining': 2,
                    'unit': 'MINUTE'
                },
                {
                    'regex': '.*',
                    'nextAvailable': '2011-07-21T18:17:06Z',
                    'uri': '*',
                    'value': 10,
                    'verb': 'GET',
                    'remaining': 2,
                    'unit': 'MINUTE'
                }
            ]
        }

        self.assertEqual(expected, view._data)


class TestLimiter(limits.Limiter):
    """Note: This was taken from Nova"""
    pass


class LimitMiddlewareTest(BaseLimitTestSuite):
    """
    Tests for the `limits.RateLimitingMiddleware` class.
    """

    @webob.dec.wsgify
    def _empty_app(self, request):
        """Do-nothing WSGI app."""
        pass

    def setUp(self):
        """Prepare middleware for use through fake WSGI app."""
        super(LimitMiddlewareTest, self).setUp()
        _limits = '(GET, *, .*, 1, MINUTE)'
        self.app = limits.RateLimitingMiddleware(self._empty_app, _limits,
                                                 "%s.TestLimiter" %
                                                 self.__class__.__module__)

    def test_limit_class(self):
        # Test that middleware selected correct limiter class.
        assert isinstance(self.app._limiter, TestLimiter)

    def test_good_request(self):
        # Test successful GET request through middleware.
        request = webob.Request.blank("/")
        response = request.get_response(self.app)
        self.assertEqual(200, response.status_int)

    def test_limited_request_json(self):
        # Test a rate-limited (413) GET request through middleware.
        request = webob.Request.blank("/")
        response = request.get_response(self.app)
        self.assertEqual(200, response.status_int)

        request = webob.Request.blank("/")
        response = request.get_response(self.app)
        self.assertEqual(response.status_int, 413)

        self.assertTrue('Retry-After' in response.headers)
        retry_after = int(response.headers['Retry-After'])
        self.assertAlmostEqual(retry_after, 60, 1)

        body = jsonutils.loads(response.body)
        expected = "Only 1 GET request(s) can be made to * every minute."
        value = body["overLimit"]["details"].strip()
        self.assertEqual(value, expected)

        self.assertTrue("retryAfter" in body["overLimit"])
        retryAfter = body["overLimit"]["retryAfter"]
        self.assertEqual(retryAfter, "60")


class LimitTest(BaseLimitTestSuite):
    """
    Tests for the `limits.Limit` class.
    """

    def test_GET_no_delay(self):
        # Test a limit handles 1 GET per second.
        limit = Limit("GET", "*", ".*", 1, 1)

        limit._get_time = MagicMock(return_value=0.0)
        delay = limit("GET", "/anything")
        self.assertEqual(None, delay)
        self.assertEqual(0, limit.next_request)
        self.assertEqual(0, limit.last_request)

    def test_GET_delay(self):
        # Test two calls to 1 GET per second limit.
        limit = Limit("GET", "*", ".*", 1, 1)
        limit._get_time = MagicMock(return_value=0.0)

        delay = limit("GET", "/anything")
        self.assertEqual(None, delay)

        delay = limit("GET", "/anything")
        self.assertEqual(1, delay)
        self.assertEqual(1, limit.next_request)
        self.assertEqual(0, limit.last_request)

        limit._get_time = MagicMock(return_value=4.0)

        delay = limit("GET", "/anything")
        self.assertEqual(None, delay)
        self.assertEqual(4, limit.next_request)
        self.assertEqual(4, limit.last_request)


class ParseLimitsTest(BaseLimitTestSuite):
    """
    Tests for the default limits parser in the in-memory
    `limits.Limiter` class.
    """

    def test_invalid(self):
        # Test that parse_limits() handles invalid input correctly.
        self.assertRaises(ValueError, limits.Limiter.parse_limits,
                          ';;;;;')

    def test_bad_rule(self):
        # Test that parse_limits() handles bad rules correctly.
        self.assertRaises(ValueError, limits.Limiter.parse_limits,
                          'GET, *, .*, 20, minute')

    def test_missing_arg(self):
        # Test that parse_limits() handles missing args correctly.
        self.assertRaises(ValueError, limits.Limiter.parse_limits,
                          '(GET, *, .*, 20)')

    def test_bad_value(self):
        # Test that parse_limits() handles bad values correctly.
        self.assertRaises(ValueError, limits.Limiter.parse_limits,
                          '(GET, *, .*, foo, minute)')

    def test_bad_unit(self):
        # Test that parse_limits() handles bad units correctly.
        self.assertRaises(ValueError, limits.Limiter.parse_limits,
                          '(GET, *, .*, 20, lightyears)')

    def test_multiple_rules(self):
        # Test that parse_limits() handles multiple rules correctly.
        try:
            l = limits.Limiter.parse_limits('(get, *, .*, 20, minute);'
                                            '(PUT, /foo*, /foo.*, 10, hour);'
                                            '(POST, /bar*, /bar.*, 5, second);'
                                            '(Say, /derp*, /derp.*, 1, day)')
        except ValueError as e:
            assert False, str(e)

        # Make sure the number of returned limits are correct
        self.assertEqual(len(l), 4)

        # Check all the verbs...
        expected = ['GET', 'PUT', 'POST', 'SAY']
        self.assertEqual([t.verb for t in l], expected)

        # ...the URIs...
        expected = ['*', '/foo*', '/bar*', '/derp*']
        self.assertEqual([t.uri for t in l], expected)

        # ...the regexes...
        expected = ['.*', '/foo.*', '/bar.*', '/derp.*']
        self.assertEqual([t.regex for t in l], expected)

        # ...the values...
        expected = [20, 10, 5, 1]
        self.assertEqual([t.value for t in l], expected)

        # ...and the units...
        expected = [limits.PER_MINUTE, limits.PER_HOUR,
                    limits.PER_SECOND, limits.PER_DAY]
        self.assertEqual([t.unit for t in l], expected)


class LimiterTest(BaseLimitTestSuite):
    """
    Tests for the in-memory `limits.Limiter` class.
    """

    def update_limits(self, delay, limit_list):
        for ln in limit_list:
            ln._get_time = Mock(return_value=delay)

    def setUp(self):
        """Run before each test."""
        super(LimiterTest, self).setUp()
        userlimits = {'user:user3': ''}

        self.update_limits(0.0, TEST_LIMITS)
        self.limiter = limits.Limiter(TEST_LIMITS, **userlimits)

    def _check(self, num, verb, url, username=None):
        """Check and yield results from checks."""
        for x in xrange(num):
            yield self.limiter.check_for_delay(verb, url, username)[0]

    def _check_sum(self, num, verb, url, username=None):
        """Check and sum results from checks."""
        results = self._check(num, verb, url, username)
        return sum(item for item in results if item)

    def test_no_delay_GET(self):
        """
        Simple test to ensure no delay on a single call for a limit verb we
        didn"t set.
        """
        delay = self.limiter.check_for_delay("GET", "/anything")
        self.assertEqual(delay, (None, None))

    def test_no_delay_PUT(self):
        # Simple test to ensure no delay on a single call for a known limit.
        delay = self.limiter.check_for_delay("PUT", "/anything")
        self.assertEqual(delay, (None, None))

    def test_delay_PUT(self):
        """
        Ensure the 11th PUT will result in a delay of 6.0 seconds until
        the next request will be granced.
        """
        expected = [None] * 10 + [6.0]
        results = list(self._check(11, "PUT", "/anything"))

        self.assertEqual(expected, results)

    def test_delay_POST(self):
        """
        Ensure the 8th POST will result in a delay of 6.0 seconds until
        the next request will be granced.
        """
        expected = [None] * 7
        results = list(self._check(7, "POST", "/anything"))
        self.assertEqual(expected, results)

        expected = 60.0 / 7.0
        results = self._check_sum(1, "POST", "/anything")
        self.assertAlmostEqual(expected, results, 8)

    def test_delay_GET(self):
        # Ensure the 11th GET will result in NO delay.
        expected = [None] * 11
        results = list(self._check(11, "GET", "/anything"))

        self.assertEqual(expected, results)

    def test_delay_PUT_wait(self):
        """
        Ensure after hitting the limit and then waiting for the correct
        amount of time, the limit will be lifted.
        """
        expected = [None] * 10 + [6.0]
        results = list(self._check(11, "PUT", "/anything"))
        self.assertEqual(expected, results)

        # Advance time
        self.update_limits(6.0, self.limiter.levels[None])

        expected = [None, 6.0]
        results = list(self._check(2, "PUT", "/anything"))
        self.assertEqual(expected, results)

    def test_multiple_delays(self):
        # Ensure multiple requests still get a delay.
        expected = [None] * 10 + [6.0] * 10
        results = list(self._check(20, "PUT", "/anything"))
        self.assertEqual(expected, results)

        self.update_limits(1.0, self.limiter.levels[None])

        expected = [5.0] * 10
        results = list(self._check(10, "PUT", "/anything"))
        self.assertEqual(expected, results)

    def test_user_limit(self):
        # Test user-specific limits.
        self.assertEqual(self.limiter.levels['user3'], [])

    def test_multiple_users(self):
        # Tests involving multiple users.
        # User1
        self.update_limits(0.0, self.limiter.levels["user1"])
        expected = [None] * 10 + [6.0] * 10
        results = list(self._check(20, "PUT", "/anything", "user1"))
        self.assertEqual(expected, results)

        # User2
        expected = [None] * 10 + [6.0] * 5
        results = list(self._check(15, "PUT", "/anything", "user2"))
        self.assertEqual(expected, results)

        # User3
        expected = [None] * 20
        results = list(self._check(20, "PUT", "/anything", "user3"))
        self.assertEqual(expected, results)

        # User1 again
        self.update_limits(1.0, self.limiter.levels["user1"])
        expected = [5.0] * 10
        results = list(self._check(10, "PUT", "/anything", "user1"))
        self.assertEqual(expected, results)

        # User2 again
        self.update_limits(2.0, self.limiter.levels["user2"])
        expected = [4.0] * 5
        results = list(self._check(5, "PUT", "/anything", "user2"))
        self.assertEqual(expected, results)


class WsgiLimiterTest(BaseLimitTestSuite):
    """
    Tests for `limits.WsgiLimiter` class.
    """

    def setUp(self):
        """Run before each test."""
        super(WsgiLimiterTest, self).setUp()
        self.app = limits.WsgiLimiter(TEST_LIMITS)

    def _request_data(self, verb, path):
        """Get data describing a limit request verb/path."""
        return jsonutils.dumps({"verb": verb, "path": path})

    def _request(self, verb, url, username=None):
        """Make sure that POSTing to the given url causes the given username
        to perform the given action.  Make the internal rate limiter return
        delay and make sure that the WSGI app returns the correct response.
        """
        if username:
            request = webob.Request.blank("/%s" % username)
        else:
            request = webob.Request.blank("/")

        request.method = "POST"
        request.body = self._request_data(verb, url)
        response = request.get_response(self.app)

        if "X-Wait-Seconds" in response.headers:
            self.assertEqual(response.status_int, 403)
            return response.headers["X-Wait-Seconds"]

        self.assertEqual(response.status_int, 204)

    def test_invalid_methods(self):
        # Only POSTs should work.
        for method in ["GET", "PUT", "DELETE", "HEAD", "OPTIONS"]:
            request = webob.Request.blank("/", method=method)
            response = request.get_response(self.app)
            self.assertEqual(response.status_int, 405)

    def test_good_url(self):
        delay = self._request("GET", "/something")
        self.assertEqual(delay, None)

    def test_escaping(self):
        delay = self._request("GET", "/something/jump%20up")
        self.assertEqual(delay, None)

    def test_response_to_delays(self):
        delay = self._request("GET", "/delayed")
        self.assertEqual(delay, None)

        delay = self._request("GET", "/delayed")
        self.assertAlmostEqual(float(delay), 60, 1)

    def test_response_to_delays_usernames(self):
        delay = self._request("GET", "/delayed", "user1")
        self.assertEqual(delay, None)

        delay = self._request("GET", "/delayed", "user2")
        self.assertEqual(delay, None)

        delay = self._request("GET", "/delayed", "user1")
        self.assertAlmostEqual(float(delay), 60, 1)

        delay = self._request("GET", "/delayed", "user2")
        self.assertAlmostEqual(float(delay), 60, 1)


class FakeHttplibSocket(object):
    """
    Fake `httplib.HTTPResponse` replacement.
    """

    def __init__(self, response_string):
        """Initialize new `FakeHttplibSocket`."""
        self._buffer = StringIO.StringIO(response_string)

    def makefile(self, _mode, _other):
        """Returns the socket's internal buffer."""
        return self._buffer


class FakeHttplibConnection(object):
    """
    Fake `httplib.HTTPConnection`.
    """

    def __init__(self, app, host):
        """
        Initialize `FakeHttplibConnection`.
        """
        self.app = app
        self.host = host

    def request(self, method, path, body="", headers=None):
        """
        Requests made via this connection actually get translated and routed
        into our WSGI app, we then wait for the response and turn it back into
        an `httplib.HTTPResponse`.
        """
        if not headers:
            headers = {}

        req = webob.Request.blank(path)
        req.method = method
        req.headers = headers
        req.host = self.host
        req.body = body

        resp = str(req.get_response(self.app))
        resp = "HTTP/1.0 %s" % resp
        sock = FakeHttplibSocket(resp)
        self.http_response = httplib.HTTPResponse(sock)
        self.http_response.begin()

    def getresponse(self):
        """Return our generated response from the request."""
        return self.http_response


def wire_HTTPConnection_to_WSGI(host, app):
    """Monkeypatches HTTPConnection so that if you try to connect to host, you
    are instead routed straight to the given WSGI app.

    After calling this method, when any code calls

    httplib.HTTPConnection(host)

    the connection object will be a fake.  Its requests will be sent directly
    to the given WSGI app rather than through a socket.

    Code connecting to hosts other than host will not be affected.

    This method may be called multiple times to map different hosts to
    different apps.

    This method returns the original HTTPConnection object, so that the caller
    can restore the default HTTPConnection interface (for all hosts).
    """

    class HTTPConnectionDecorator(object):
        """Wraps the real HTTPConnection class so that when you instantiate
            the class you might instead get a fake instance.
        """

        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __call__(self, connection_host, *args, **kwargs):
            if connection_host == host:
                return FakeHttplibConnection(app, host)
            else:
                return self.wrapped(connection_host, *args, **kwargs)

    oldHTTPConnection = httplib.HTTPConnection
    httplib.HTTPConnection = HTTPConnectionDecorator(httplib.HTTPConnection)
    return oldHTTPConnection


class WsgiLimiterProxyTest(BaseLimitTestSuite):
    """
    Tests for the `limits.WsgiLimiterProxy` class.
    """

    def setUp(self):
        """
        Do some nifty HTTP/WSGI magic which allows for WSGI to be called
        directly by something like the `httplib` library.
        """
        super(WsgiLimiterProxyTest, self).setUp()
        self.app = limits.WsgiLimiter(TEST_LIMITS)
        self.oldHTTPConnection = (
            wire_HTTPConnection_to_WSGI("169.254.0.1:80", self.app))
        self.proxy = limits.WsgiLimiterProxy("169.254.0.1:80")

    def test_200(self):
        # Successful request test.
        delay = self.proxy.check_for_delay("GET", "/anything")
        self.assertEqual(delay, (None, None))

    def test_403(self):
        # Forbidden request test.
        delay = self.proxy.check_for_delay("GET", "/delayed")
        self.assertEqual(delay, (None, None))

        delay, error = self.proxy.check_for_delay("GET", "/delayed")
        error = error.strip()

        self.assertAlmostEqual(float(delay), 60, 1)
        self.assertEqual(error, "403 Forbidden\n\nOnly 1 GET request(s) can be"
                                " made to /delayed every minute.")

    def tearDown(self):
        # restore original HTTPConnection object
        httplib.HTTPConnection = self.oldHTTPConnection
        super(WsgiLimiterProxyTest, self).tearDown()


class LimitsViewTest(testtools.TestCase):
    def setUp(self):
        super(LimitsViewTest, self).setUp()

    def test_empty_data(self):
        """
        Test the default returned results if an empty dictionary is given
        """
        rate_limit = {}
        view = views.LimitView(rate_limit)
        self.assertIsNotNone(view)

        data = view.data()
        expected = {'limit': {'regex': '',
                              'nextAvailable': '1970-01-01T00:00:00Z',
                              'uri': '',
                              'value': '',
                              'verb': '',
                              'remaining': 0,
                              'unit': ''}}

        self.assertEqual(expected, data)

    def test_data(self):
        """
        Test the returned results for a fully populated dictionary
        """
        rate_limit = {
            "URI": "*",
            "regex": ".*",
            "value": 10,
            "verb": "POST",
            "remaining": 2,
            "unit": "MINUTE",
            "resetTime": 1311272226
        }

        view = views.LimitView(rate_limit)
        self.assertIsNotNone(view)

        data = view.data()
        expected = {'limit': {'regex': '.*',
                              'nextAvailable': '2011-07-21T18:17:06Z',
                              'uri': '*',
                              'value': 10,
                              'verb': 'POST',
                              'remaining': 2,
                              'unit': 'MINUTE'}}

        self.assertEqual(expected, data)


class LimitsViewsTest(testtools.TestCase):
    def setUp(self):
        super(LimitsViewsTest, self).setUp()

    def test_empty_data(self):
        rate_limits = []
        abs_view = dict()

        view_data = views.LimitViews(abs_view, rate_limits)
        self.assertIsNotNone(view_data)

        data = view_data.data()
        expected = {'limits': [{'verb': 'ABSOLUTE'}]}

        self.assertEqual(expected, data)

    def test_data(self):
        rate_limits = [
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "POST",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            },
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "PUT",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            },
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "DELETE",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            },
            {
                "URI": "*",
                "regex": ".*",
                "value": 10,
                "verb": "GET",
                "remaining": 2,
                "unit": "MINUTE",
                "resetTime": 1311272226
            }
        ]
        abs_view = {"instances": 55, "volumes": 100, "backups": 40}

        view_data = views.LimitViews(abs_view, rate_limits)
        self.assertIsNotNone(view_data)

        data = view_data.data()
        expected = {'limits': [{'max_instances': 55,
                                'max_backups': 40,
                                'verb': 'ABSOLUTE',
                                'max_volumes': 100},
                               {'regex': '.*',
                                'nextAvailable': '2011-07-21T18:17:06Z',
                                'uri': '*',
                                'value': 10,
                                'verb': 'POST',
                                'remaining': 2, 'unit': 'MINUTE'},
                               {'regex': '.*',
                                'nextAvailable': '2011-07-21T18:17:06Z',
                                'uri': '*',
                                'value': 10,
                                'verb': 'PUT',
                                'remaining': 2,
                                'unit': 'MINUTE'},
                               {'regex': '.*',
                                'nextAvailable': '2011-07-21T18:17:06Z',
                                'uri': '*',
                                'value': 10,
                                'verb': 'DELETE',
                                'remaining': 2,
                                'unit': 'MINUTE'},
                               {'regex': '.*',
                                'nextAvailable': '2011-07-21T18:17:06Z',
                                'uri': '*',
                                'value': 10,
                                'verb': 'GET',
                                'remaining': 2, 'unit': 'MINUTE'}]}

        self.assertEqual(expected, data)
