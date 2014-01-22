# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
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

from proboscis import test
from proboscis import SkipTest
from functools import wraps

from troveclient.compat.client import TroveHTTPClient
from trove.tests.api.versions import Versions


@test(groups=['dbaas.api.headers'])
def must_work_with_blank_accept_headers():
    """Test to make sure that trove works without the headers"""
    versions = Versions()
    versions.setUp()
    client = versions.client

    if type(client.client).morph_request != TroveHTTPClient.morph_request:
        raise SkipTest("Not using the JSON client so can't execute this test.")

    original_morph_request = client.client.morph_request

    def morph_content_type_to(content_type):
        @wraps(original_morph_request)
        def _morph_request(kwargs):
            original_morph_request(kwargs)
            kwargs['headers']['Accept'] = content_type
            kwargs['headers']['Content-Type'] = content_type

        client.client.morph_request = _morph_request

    try:
        morph_content_type_to('')
        # run versions to make sure the API still returns JSON even though the
        # header type is blank
        versions.test_list_versions_index()
    finally:
        client.client.morph_request = original_morph_request
