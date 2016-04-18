#    Copyright 2014 Rackspace
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

import json
import os
import re
import time

from proboscis.asserts import fail
from six.moves.urllib.parse import urlparse
from troveclient.compat.client import TroveHTTPClient

from trove.tests.config import CONFIG

print_req = True


def shorten_url(url):
    parsed = urlparse(url)
    if parsed.query:
        method_url = parsed.path + '?' + parsed.query
    else:
        method_url = parsed.path
    return method_url


class SnippetWriter(object):

    def __init__(self, conf, get_replace_list):
        self.conf = conf
        self.get_replace_list = get_replace_list

    def output_request(self, user_details, name, url, output_headers, body,
                       content_type, method, static_auth_token=True):
        headers = []
        parsed = urlparse(url)
        method_url = shorten_url(url)
        headers.append("%s %s HTTP/1.1" % (method, method_url))
        headers.append("User-Agent: %s" % output_headers['User-Agent'])
        headers.append("Host: %s" % parsed.netloc)
        # static_auth_token option for documentation purposes
        if static_auth_token:
            output_token = '87c6033c-9ff6-405f-943e-2deb73f278b7'
        else:
            output_token = output_headers['X-Auth-Token']
        headers.append("X-Auth-Token: %s" % output_token)
        headers.append("Accept: %s" % output_headers['Accept'])
        print("OUTPUT HEADERS: %s" % output_headers)
        headers.append("Content-Type: %s" % output_headers['Content-Type'])
        self.write_file(user_details, name, "-%s.txt" % content_type, url,
                        method, "request", output='\n'.join(headers))

        pretty_body = self.format_body(body, content_type)
        self.write_file(user_details, name, ".%s" % content_type, url,
                        method, "request", output=pretty_body)

    def output_response(self, user_details, name, content_type, url, method,
                        resp, body):
        version = "1.1"  # if resp.version == 11 else "1.0"
        lines = [
            ["HTTP/%s %s %s" % (version, resp.status, resp.reason)],
            ["Content-Type: %s" % resp['content-type']],
        ]
        if 'via' in resp:
            lines.append(["Via: %s" % resp['via']])
        lines.append(["Content-Length: %s" % resp['content-length']])
        lines.append(["Date: Mon, 18 Mar 2013 19:09:17 GMT"])
        if 'server' in resp:
            lines.append(["Server: %s" % resp["server"]])

        new_lines = [x[0] for x in lines]
        joined_lines = '\n'.join(new_lines)

        self.write_file(user_details, name, "-%s.txt" % content_type, url,
                        method, "response", output=joined_lines)

        if body:
            pretty_body = self.format_body(body, content_type)
            self.write_file(user_details, name, ".%s" % content_type, url,
                            method, "response", output=pretty_body)

    def format_body(self, body, content_type):
        assert content_type == 'json'
        try:
            if self.conf['replace_dns_hostname']:
                before = r'\"hostname\": \"[a-zA-Z0-9-_\.]*\"'
                after = '\"hostname\": \"%s\"' % self.conf[
                    'replace_dns_hostname']
                body = re.sub(before, after, body)
            return json.dumps(json.loads(body), sort_keys=True, indent=4)
        except Exception:
            return body or ''

    def write_request_file(self, user_details, name, content_type, url, method,
                           req_headers, request_body):
        if print_req:
            print("\t%s req url:%s" % (content_type, url))
            print("\t%s req method:%s" % (content_type, method))
            print("\t%s req headers:%s" % (content_type, req_headers))
            print("\t%s req body:%s" % (content_type, request_body))
        self.output_request(user_details, name, url, req_headers, request_body,
                            content_type, method)

    def write_response_file(self, user_details, name, content_type, url,
                            method, resp, resp_content):
        if print_req:
            print("\t%s resp:%s" % (content_type, resp))
            print("\t%s resp content:%s" % (content_type, resp_content))
        self.output_response(user_details, name, content_type, url, method,
                             resp, resp_content)

    def write_file(self, user_details, name, content_type, url, method,
                   in_or_out, output):
        output = output.replace(user_details['tenant'], '1234')
        if self.conf['replace_host']:
            output = output.replace(user_details['api_url'],
                                    self.conf['replace_host'])
            pre_host_port = urlparse(user_details['service_url']).netloc
            post_host = urlparse(self.conf['replace_host']).netloc
            output = output.replace(pre_host_port, post_host)
        output = output.replace("fake_host", "hostname")
        output = output.replace("FAKE_", "")
        for resource in self.get_replace_list():
            output = output.replace(str(resource[0]), str(resource[1]))
        filename = "%s/db-%s-%s%s" % (self.conf['directory'],
                                      name.replace('_', '-'), in_or_out,
                                      content_type)
        self._write_file(filename, output)

    def _write_file(self, filename, output):
        empty = len(output.strip()) == 0
        # Manipulate actual data to appease doc niceness checks
        actual = [line.rstrip() for line in output.split("\n")]
        if not empty and actual[len(actual) - 1] != '':
            actual.append("")

        def goofy_diff(a, b):
            diff = []
            for i in range(len(a)):
                if i < len(b):
                    if a[i].rstrip() != b[i].rstrip():
                        diff.append('Expected line %d :%s\n'
                                    '  Actual line %d :%s'
                                    % (i + 1, a[i], i + 1, b[i]))
                else:
                    diff.append("Expected line %d :%s" % (i + 1, a[i]))
            for j in range(len(b) - len(a)):
                i2 = len(a) + j
                diff.append("  Actual line %d :%s" % (i2 + 1, b[i2]))
            return diff

        def write_actual_file():
            # Always write the file.
            with open(filename, "w") as file:
                for line in actual:
                    file.write("%s\n" % line)

        def assert_output_matches():
            if os.path.isfile(filename):
                with open(filename, 'r') as original_file:
                    original = original_file.read()
                    if empty:
                        fail('Error: output missing in new snippet generation '
                             'for %s. Old content follows:\n"""%s"""'
                             % (filename, original))
                    elif filename.endswith('.json'):
                        assert_json_matches(original)
                    else:
                        assert_file_matches(original)
            elif not empty:
                fail('Error: new file necessary where there was no file '
                     'before. Filename=%s\nContent follows:\n"""%s"""'
                     % (filename, output))

        def assert_file_matches(original):
            expected = original.split('\n')
            # Remove the last item which will look like a duplicated
            # file ending newline
            expected.pop()
            diff = '\n'.join(goofy_diff(expected, actual))
            if diff:
                fail('Error: output files differ for %s:\n%s'
                     % (filename, diff))

        def order_json(json_obj):
            """Sort the json object so that it can be compared properly."""
            if isinstance(json_obj, list):
                return sorted(order_json(elem) for elem in json_obj)
            if isinstance(json_obj, dict):
                return sorted(
                    (key, order_json(value))
                    for key, value in json_obj.items())
            else:
                return json_obj

        def assert_json_matches(original):
            try:
                expected_json = json.loads(original)
                actual_json = json.loads(output)
            except ValueError:
                fail('Invalid json!\nExpected: %s\nActual: %s'
                     % (original, output))

            if order_json(expected_json) != order_json(actual_json):
                # Re-Use the same failure output if the json is different
                assert_file_matches(original)

        if not os.environ.get('TESTS_FIX_EXAMPLES'):
            assert_output_matches()
        elif not empty:
            write_actual_file()


# This method is mixed into the client class.
# It requires the following fields: snippet_writer, content_type, and
# "name," the last of which must be set before each call.
def write_to_snippet(self, args, kwargs, resp, body):
    if self.name is None:
        raise RuntimeError("'name' not set before call.")
    url = args[0]
    method = args[1]
    request_headers = kwargs['headers']
    request_body = kwargs.get('body', None)
    response_headers = resp
    response_body = body

    # Log request
    user_details = {
        'api_url': self.service_url,
        'service_url': self.service_url,
        'tenant': self.tenant,
    }
    self.snippet_writer.write_request_file(user_details, self.name,
                                           self.content_type, url, method,
                                           request_headers, request_body)
    self.snippet_writer.write_response_file(user_details, self.name,
                                            self.content_type, url, method,
                                            response_headers, response_body)

    # Create a short url to assert against.
    short_url = url
    base_url = self.service_url
    for prefix in (base_url):
        if short_url.startswith(prefix):
            short_url = short_url[len(prefix):]
    self.old_info = {
        'url': shorten_url(short_url),
        'method': method,
        'request_headers': request_headers,
        'request_body': request_body,
        'response_headers': response_headers,
        'response_body': response_body
    }


def add_fake_response_headers(headers):
    """
    Fakes other items that would appear if you were using, just to make up
    an example, a proxy.
    """
    conf = CONFIG.examples
    if 'via' in conf and 'via' not in headers:
        headers['via'] = conf['via']
    if 'server' in conf and 'server' not in headers:
        headers['server'] = conf['server']
    if 'date' not in headers:
        date_string = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
        headers['date'] = date_string


class JsonClient(TroveHTTPClient):

    content_type = 'json'

    def http_log(self, args, kwargs, resp, body):
        add_fake_response_headers(resp)
        self.pretty_log(args, kwargs, resp, body)

        def write_snippet():
            return write_to_snippet(self, args, kwargs, resp, body)

        self.write_snippet = write_snippet
