#    Copyright 2013 OpenStack Foundation
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

import testtools

from reddwarf.common.wsgi import Router, Fault

from routes import Mapper


class FakeRequst(object):
    """A fake webob request object designed to cause 404.

    The dispatcher actually checks if the given request is a dict and throws
    an error if it is. This object wrapper tricks the dispatcher into
    handling the request like a regular request.
    """

    environ = {
        "wsgiorg.routing_args": [
            False,
            False
        ]
    }


class TestRouter(testtools.TestCase):
    """Test case for trove `Router` extensions."""

    def setUp(self):
        super(TestRouter, self).setUp()
        self.mapper = Mapper()

    def test_404_is_fault(self):
        """Test that the dispatcher wraps 404's in a `Fault`."""

        fake_request = FakeRequst()

        response = Router._dispatch(fake_request)

        assert isinstance(response, Fault)
