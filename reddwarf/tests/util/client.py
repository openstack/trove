# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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
.. moduleauthor:: Nirmal Ranganathan <nirmal.ranganathan@rackspace.com>
.. moduleauthor:: Tim Simpson <tim.simpson@rackspace.com>
"""


from proboscis.asserts import *
from reddwarf.tests.config import CONFIG
from reddwarfclient.xml import ReddwarfXmlClient
from reddwarf.openstack.common import processutils


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
        assert_equal(resp.status, expected_http_code)

    @property
    def last_http_code(self):
        resp, body = self.real_client.client.last_response
        return resp.status

    @staticmethod
    def find_flavor_self_href(flavor):
        self_links = [link for link in flavor.links if link['rel'] == 'self']
        assert_true(len(self_links) > 0, "Flavor had no self href!")
        flavor_href = self_links[0]['href']
        assert_false(flavor_href is None, "Flavor link self href missing.")
        return flavor_href

    def find_flavors_by(self, condition, flavor_manager=None):
        flavor_manager = flavor_manager or self.flavors
        flavors = flavor_manager.list()
        return [flavor for flavor in flavors if condition(flavor)]

    def find_flavors_by_name(self, name, flavor_manager=None):
        return self.find_flavors_by(lambda flavor: flavor.name == name,
                                    flavor_manager)

    def find_flavors_by_ram(self, ram, flavor_manager=None):
        return self.find_flavors_by(lambda flavor: flavor.ram == ram,
                                    flavor_manager)

    def find_flavor_and_self_href(self, flavor_id, flavor_manager=None):
        """Given an ID, returns flavor and its self href."""
        flavor_manager = flavor_manager or self.flavors
        assert_false(flavor_id is None)
        flavor = flavor_manager.get(flavor_id)
        assert_false(flavor is None)
        flavor_href = self.find_flavor_self_href(flavor)
        return flavor, flavor_href

    def find_image_and_self_href(self, image_id):
        """Given an ID, returns tuple with image and its self href."""
        assert_false(image_id is None)
        image = self.images.get(image_id)
        assert_true(image is not None)
        self_links = [link['href'] for link in image.links
                      if link['rel'] == 'self']
        assert_true(len(self_links) > 0,
                    "Found image with ID %s but it had no self link!" %
                    str(image_id))
        image_href = self_links[0]
        assert_false(image_href is None, "Image link self href missing.")
        return image, image_href

    def __getattr__(self, item):
        return getattr(self.real_client, item)


def call_xmllint(name, body):
    try:
        with open(CONFIG.xml_temp_file, 'w') as file:
            file.write(body)

        #if CONFIG.get('xml_xsd', None):
        args = [CONFIG.xml_temp_file]
        if CONFIG.get('xml_xsd', None):
            args += ["--schema", CONFIG.xml_xsd]
        output = processutils.execute(CONFIG.xmllint_bin, *args,
                                      check_exit_code=0, shell=False)
    except processutils.ProcessExecutionError as pe:
        fail("Error validating XML! %s" % pe)


class XmlLintClient(ReddwarfXmlClient):

    content_type = 'xml'

    def http_log(self, args, kwargs, resp, body):
        #self.pretty_log(args, kwargs, resp, body)
        if kwargs.get('body', None):
            call_xmllint("request", kwargs['body'])
        if body:
            call_xmllint("response", body)
