# Copyright (c) 2011 OpenStack Foundation
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
:mod:`tests` -- Utility methods for tests.
===================================

.. automodule:: utils
   :platform: Unix
   :synopsis: Tests for Nova.
"""


from proboscis import asserts

from trove.tests.config import CONFIG


def add_report_event_to(home, name):
    """Takes a module, class, etc, and an attribute name to decorate."""
    func = getattr(home, name)

    def __cb(*args, **kwargs):
        # While %s turns a var into a string but in some rare cases explicit
        # str() is less likely to raise an exception.
        arg_strs = [repr(arg) for arg in args]
        arg_strs += ['%s=%s' % (repr(key), repr(value))
                     for (key, value) in kwargs.items()]
        CONFIG.get_reporter().log("[RDC] Calling : %s(%s)..."
                                  % (name, ','.join(arg_strs)))
        value = func(*args, **kwargs)
        CONFIG.get_reporter.log("[RDC]     returned %s." % str(value))
        return value
    setattr(home, name, __cb)


class TestClient(object):
    """Decorates the rich clients with some extra methods.

    These methods are filled with test asserts, meaning if you use this you
    get the tests for free.

    """

    def __init__(self, real_client):
        """Accepts a normal client."""
        self.real_client = real_client

    def assert_http_code(self, expected_http_code):
        resp, body = self.real_client.client.last_response
        asserts.assert_equal(resp.status, expected_http_code)

    @property
    def last_http_code(self):
        resp, body = self.real_client.client.last_response
        return resp.status

    def __getattr__(self, item):
        if item == "__setstate__":
            raise AttributeError(item)
        if hasattr(self.real_client, item):
            return getattr(self.real_client, item)
        raise AttributeError(item)
