import json
import os
import re
from six.moves.urllib.parse import urlparse
import xml.dom.minidom

from proboscis.asserts import *
from troveclient.compat.client import TroveHTTPClient
from troveclient.compat.xml import TroveXmlClient


print_req = True


class ConfigFile(object):

    def __init__(self, config_file):
        if not os.path.exists(config_file):
            raise RuntimeError("Could not find Example CONF at %s." %
                               config_file)
        file_contents = open(config_file, "r").read()
        try:
            config = json.loads(file_contents)
        except Exception as exception:
            msg = 'Error loading config file "%s".' % config_file
            raise RuntimeError(msg, exception)

        self.directory = config.get("directory", None)
        if not self.directory.endswith('/'):
            self.directory += '/'
        self.api_url = config.get("api_url", None)
        self.auth_url = config.get("auth_url", None)
        self.username = config.get("username", None)
        self.password = config.get("password", None)
        self.tenant = config.get("tenant", None)
        self.replace_host = config.get("replace_host", None)
        self.replace_dns_hostname = config.get("replace_dns_hostname", None)
        if self.auth_url:
            auth_id, tenant_id = self.get_auth_token_id_tenant_id(self.auth_url,
                                                                  self.username,
                                                                  self.password)
        else:
            auth_id = self.tenant
            tenant_id = self.tenant

        print("id = %s" % auth_id)
        self.headers = {
            'X-Auth-Token': str(auth_id)
        }
        print("tenantID = %s" % tenant_id)
        self.tenantID = tenant_id
        self.dbaas_url = "%s/v1.0/%s" % (self.api_url, self.tenantID)


def shorten_url(url):
    parsed = urlparse(url)
    if parsed.query:
        method_url = parsed.path + '?' + parsed.query
    else:
        method_url = parsed.path
    return method_url


class SnippetWriter(object):

    def __init__(self, conf):
        self.conf = conf

    def _indent_xml(self, my_string):
        my_string = my_string.encode("utf-8")
        # convert to plain string without indents and spaces
        my_re = re.compile(r'>\s+([^\s])', re.DOTALL)
        my_string = myre.sub(r'>\g<1>', my_string)
        my_string = xml.dom.minidom.parseString(my_string).toprettyxml()
        # remove line breaks
        my_re = re.compile(r'>\n\s+([^<>\s].*?)\n\s+</', re.DOTALL)
        my_string = my_re.sub(r'>\g<1></', my_string)
        return my_string

    def output_request(self, url, output_headers, body, content_type, method,
                       static_auth_token=True):
        output_list = []
        parsed = urlparse(url)
        method_url = shorten_url(url)
        output_list.append("%s %s HTTP/1.1" % (method, method_url))
        output_list.append("User-Agent: %s" % output_headers['User-Agent'])
        output_list.append("Host: %s" % parsed.netloc)
        # static_auth_token option for documentation purposes
        if static_auth_token:
            output_token = '87c6033c-9ff6-405f-943e-2deb73f278b7'
        else:
            output_token = output_headers['X-Auth-Token']
        output_list.append("X-Auth-Token: %s" % output_token)
        output_list.append("Accept: %s" % output_headers['Accept'])
        print("OUTPUT HEADERS: %s" % output_headers)
        output_list.append("Content-Type: %s" % output_headers['Content-Type'])
        output_list.append("")
        pretty_body = self.format_body(body, content_type)
        output_list.append("%s" % pretty_body)
        output_list.append("")
        return '\n'.join(output_list)

    def output_response(self, resp, body, content_type):
        output_list = []
        version = "1.1" if resp.version == 11 else "1.0"
        lines = [
            ["HTTP/%s %s %s" % (version, resp.status, resp.reason)],
            ["Content-Type: %s" % resp['content-type']],
            ["Content-Length: %s" % resp['content-length']],
            ["Date: %s" % resp['date']]]
        new_lines = [x[0] for x in lines]
        joined_lines = '\n'.join(new_lines)
        output_list.append(joined_lines)
        if body:
            output_list.append("")
            pretty_body = self.format_body(body, content_type)
            output_list.append("%s" % pretty_body)
        output_list.append("")
        return '\n'.join(output_list)

    def format_body(self, body, content_type):
        if content_type == 'json':
            try:
                if self.conf.replace_dns_hostname:
                    before = r'\"hostname\": \"[a-zA-Z0-9-_\.]*\"'
                    after = '\"hostname\": \"%s\"' % self.conf.replace_dns_hostname
                    body = re.sub(before, after, body)
                return json.dumps(json.loads(body), sort_keys=True, indent=4)
            except Exception:
                return body or ''
        else:
            # expected type of body is xml
            try:
                if self.conf.replace_dns_hostname:
                    hostname = 'hostname=\"%s\"' % self.conf.replace_dns_hostname,
                    body = re.sub(r'hostname=\"[a-zA-Z0-9-_\.]*\"',
                                  hostname, body)
                return self._indent_xml(body)
            except Exception as ex:
                return body if body else ''


    def write_request_file(self, name, content_type, url, method,
                           req_headers, request_body):
        def write_request():
            return self.output_request(url, req_headers, request_body,
                                       content_type, method)
        if print_req:
            print("\t%s req url:%s" % (content_type, url))
            print("\t%s req method:%s" % (content_type, method))
            print("\t%s req headers:%s" % (content_type, req_headers))
            print("\t%s req body:%s" % (content_type, request_body))
        self.write_file(name, content_type, url, method, "request",
                        write_request)

    def write_response_file(self, name, content_type, url, method,
                           resp, resp_content):
        def write_response():
            return self.output_response(resp, resp_content, content_type)
        self.write_file(name, content_type, url, method, "response",
                        write_response)
        if print_req:
            print("\t%s resp:%s" % (content_type, resp))
            print("\t%s resp content:%s" % (content_type, resp_content))

    def write_file(self, name, content_type, url, method, in_or_out, func):
        filename = "%sdb-%s-%s.%s" % (self.conf.directory,
                                      name.replace('_', '-'), in_or_out,
                                      content_type)
        with open(filename, "w") as file:
            output = func()
            output = output.replace(self.conf.tenantID, '1234')
            if self.conf.replace_host:
                output = output.replace(self.conf.api_url, self.conf.replace_host)
                pre_host_port = urlparse(self.conf.api_url).netloc
                post_host = urlparse(self.conf.replace_host).netloc
                output = output.replace(pre_host_port, post_host)
            output = output.replace("fake_host", "hostname")
            output = output.replace("FAKE_", "")

            file.write(output)


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
    self.snippet_writer.write_request_file(self.name, self.content_type,
        url, method, request_headers, request_body)
    self.snippet_writer.write_response_file(self.name, self.content_type,
        url, method, response_headers, response_body)

    # Create a short url to assert against.
    short_url = url
    for prefix in (self.snippet_writer.conf.dbaas_url,
                   self.snippet_writer.conf.api_url):
        if short_url.startswith(prefix):
            short_url = short_url[len(prefix):]
    self.old_info = {
        'url':shorten_url(short_url),
        'method': method,
        'request_headers':request_headers,
        'request_body':request_body,
        'response_headers':response_headers,
        'response_body':response_body
        }


class JsonClient(TroveHTTPClient):

    content_type = 'json'

    def http_log(self, *args, **kwargs):
        return write_to_snippet(self, *args, **kwargs)


class XmlClient(TroveXmlClient):

    content_type = 'xml'

    def http_log(self, *args, **kwargs):
        return write_to_snippet(self, *args, **kwargs)
