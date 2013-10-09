from proboscis import test
from proboscis.asserts import *
from proboscis import SkipTest
from functools import wraps

from troveclient.compat.client import TroveHTTPClient
from trove.tests.api.versions import Versions
from troveclient.compat import exceptions


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
        # now change headers to XML to make sure the test fails
        morph_content_type_to('application/xml')
        assert_raises(exceptions.ResponseFormatError,
                      versions.test_list_versions_index)
    finally:
        client.client.morph_request = original_morph_request
