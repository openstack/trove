import httplib2
import json
import os
import re
import six
import sys
import time
from urlparse import urlparse
import xml.dom.minidom

from proboscis import before_class
from proboscis import test
from proboscis import TestProgram
from proboscis.asserts import *
from proboscis.asserts import Check

from troveclient.compat import Dbaas
from troveclient.compat import TroveHTTPClient


from client import ConfigFile
from client import SnippetWriter
from client import JsonClient
from client import XmlClient


print_req = True


class ExampleClient(object):

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
        print("directory = %s" % self.directory)
        self.api_url = config.get("api_url", None)
        print("api_url = %s" % self.api_url)
        #auth
        auth_url = config.get("auth_url", None)
        print("auth_url = %s" % auth_url)
        username = config.get("username", None)
        print("username = %s" % username)
        password = config.get("password", None)
        print("password = %s" % password)
        self.tenant = config.get("tenant", None)
        self.replace_host = config.get("replace_host", None)
        print("tenant = %s" % self.tenant)
        self.replace_dns_hostname = config.get("replace_dns_hostname", None)
        if auth_url:
            auth_id, tenant_id = self.get_auth_token_id_tenant_id(auth_url,
                                                                  username,
                                                                  password)
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
        self.write_file(name, content_type, url, method, write_request)

    def write_response_file(self, name, content_type, url, method,
                           resp, resp_content):
        def write_response():
            return self.output_response(resp, resp_content, content_type)
        self.write_file(name, content_type, url, method, write_response)
        if print_req:
            print("\t%s resp:%s" % (content_type, resp))
            print("\t%s resp content:%s" % (content_type, resp_content))

    def write_file(self, name, content_type, url, method, func):
        filename = "%sdb-%s-request.%s" % (self.directory, name, content_type)
        with open(filename, "w") as file:
            output = func()
            output = output.replace(self.tenantID, '1234')
            if self.replace_host:
                output = output.replace(self.api_url, self.replace_host)
                pre_host_port = urlparse(self.api_url).netloc
                post_host = urlparse(self.replace_host).netloc
                output = output.replace(pre_host_port, post_host)

            file.write(output)

    def version_http_call(self, name, method, json, xml,
                           output=True, print_resp=False):
        json['url'] = "%s/%s" % (self.api_url, json['url'])
        xml['url'] = "%s/%s" % (self.api_url, xml['url'])
        return self.make_request(name, method, json, xml, output, print_resp)

    def http_call(self, name, method, url, json, xml,
                  output=True, print_resp=False):
        json['url'] = "%s/%s" % (self.dbaas_url, json['url'])
        xml['url'] = "%s/%s" % (self.dbaas_url, xml['url'])
        return self.make_request(name, method, json, xml, output, print_resp)

    # print_req and print_resp for debugging purposes
    def make_request(self, name, method, json, xml,
                     output=True, print_resp=False):
        name = name.replace('_', '-')
        print("http call for %s" % name)
        http = httplib2.Http(disable_ssl_certificate_validation=True)
        req_headers = {'User-Agent': "python-example-client",
                       'Content-Type': "application/json",
                       'Accept': "application/json"
                      }
        req_headers.update(self.headers)


        content_type = 'json'
        request_body = json.get('body', None)
        url = json.get('url')
        if output:
            self.write_request_file(name, 'json', url, method, req_headers,
                                    request_body)

        resp, resp_content = http.request(url, method, body=request_body,
                                          headers=req_headers)
        json_resp = resp, resp_content
        if output:
            filename = "%sdb-%s-response.%s" % (self.directory, name,
                                                content_type)
            self.write_response_file(name, 'json', url, method, resp,
                                     resp_content)


        content_type = 'xml'
        req_headers['Accept'] = 'application/xml'
        req_headers['Content-Type'] = 'application/xml'
        request_body = xml.get('body', None)
        url = xml.get('url')
        if output:
            filename = "%sdb-%s-request.%s" % (self.directory, name,
                                               content_type)
            output = self.write_request_file(name, 'xml', url, method,
                                             req_headers, request_body)
        resp, resp_content = http.request(url, method, body=request_body,
                                          headers=req_headers)
        xml_resp = resp, resp_content
        if output:
            filename = "%sdb-%s-response.%s" % (self.directory, name,
                                                content_type)
            self.write_response_file(name, 'xml', url, method, resp,
                                     resp_content)


        return json_resp, xml_resp

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
        if parsed.query:
            method_url = parsed.path + '?' + parsed.query
        else:
            method_url = parsed.path
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
                if self.replace_dns_hostname:
                    before = r'\"hostname\": \"[a-zA-Z0-9-_\.]*\"'
                    after = '\"hostname\": \"%s\"' % self.replace_dns_hostname
                    body = re.sub(before, after, body)
                return json.dumps(json.loads(body), sort_keys=True, indent=4)
            except Exception:
                return body if body else ''
        else:
            # expected type of body is xml
            try:
                if self.replace_dns_hostname:
                    hostname = 'hostname=\"%s\"' % self.replace_dns_hostname,
                    body = re.sub(r'hostname=\"[a-zA-Z0-9-_\.]*\"',
                                  hostname, body)
                return self._indent_xml(body)
            except Exception as ex:
                return body if body else ''

    def get_auth_token_id_tenant_id(self, url, username, password):
        body = ('{"auth":{"tenantName": "%s", "passwordCredentials": '
                '{"username": "%s", "password": "%s"}}}')
        body = body % (self.tenant, username, password)
        http = httplib2.Http(disable_ssl_certificate_validation=True)
        req_headers = {'User-Agent': "python-example-client",
                       'Content-Type': "application/json",
                       'Accept': "application/json",
                      }
        resp, body = http.request(url, 'POST', body=body, headers=req_headers)
        auth = json.loads(body)
        auth_id = auth['access']['token']['id']
        tenant_id = auth['access']['token']['tenant']['id']
        return auth_id, tenant_id


@test
def load_config_file():
    global conf
    print("RUNNING ARGS :  " + str(sys.argv))
    conf = None
    for arg in sys.argv[1:]:
        conf_file_path = os.path.expanduser(arg)
        conf = ConfigFile(conf_file_path)
        return
    if not conf:
        fail("Missing conf file.")

def create_client(cls=TroveHTTPClient):
    client = Dbaas(conf.username, conf.password, tenant=conf.tenant,
                   auth_url="blah/", auth_strategy='fake',
                   insecure=True, service_type='trove',
                   service_url=conf.dbaas_url, client_cls=cls)
    return client

class ClientPair(object):
    """
    Combines a Json and XML version of the Dbaas client.
    """

    def __init__(self):
        snippet_writer = SnippetWriter(conf)
        def make_client(cls):
            client = create_client(cls)
            client.client.name = "auth"
            client.client.snippet_writer = snippet_writer
            client.authenticate()
            return client
        self.json = make_client(JsonClient)
        self.xml = make_client(XmlClient)
        self.clients = [self.json, self.xml]

    def do(self, name, url, method, status, reason, func, func_args=None):
        """
        Performs the given function twice, first for the JSON client, then for
        the XML one, and writes both to their respective files.
        'name' is the name of the file, while 'url,' 'method,' 'status,'
        and 'reason' are expected values that are asserted against.
        If func_args is present, it is a list of lists, each one of which
        is passed as the *args to the two invocations of "func".
        """
        func_args = func_args or [[], []]
        snippet_writer = SnippetWriter(conf)
        results = []
        for index, client in enumerate(self.clients):
            client.client.snippet_writer = snippet_writer
            client.client.name = name
            args = func_args[index]
            result = func(client, *args)
            with Check() as check:
                if isinstance(url, (list, tuple)):
                    check.equal(client.client.old_info['url'], url[index])
                else:
                    check.equal(client.client.old_info['url'], url)
                check.equal(client.client.old_info['method'], method)
                check.equal(client.client.old_info['response_headers'].status,
                            status)
                check.equal(client.client.old_info['response_headers'].reason,
                            reason)
            results.append(result)
            # To prevent this from writing a snippet somewhere else...
            client.client.name = "junk"

        return results


JSON_INDEX = 0
XML_INDEX = 1

@test(depends_on=[load_config_file])
class Versions(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def get_versions(self):
        self.clients.do("versions",
           "", "GET", 200, "OK",
            lambda client : client.versions.index(conf.api_url))


    @test
    def get_version(self):
        self.clients.do("versions",
            "/v1.0", "GET", 200, "OK",
            lambda client : client.versions.index(conf.api_url + "/v1.0/"))


@test(depends_on=[load_config_file])
class Flavors(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def get_flavors(self):
        self.clients.do("flavors",
            "/flavors", "GET", 200, "OK",
            lambda client : client.flavors.list())

    @test
    def get_flavor_by_id(self):
        self.clients.do("flavors_by_id",
            "/flavors/1", "GET", 200, "OK",
            lambda client : client.flavors.get(1))


@test(depends_on=[load_config_file])
def clean_slate():
    client = create_client()
    client.client.name = "list"
    instances = client.instances.list()
    assert_equal(0, len(instances), "Instance count must be zero.")


@test(depends_on=[clean_slate])
class CreateInstance(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def post_create_instance(self):
        def create_instance(client, name):
            instance = client.instances.create(name, 1, volume={'size':2},
                databases=[{
                        "name": "sampledb",
                        "character_set": "utf8",
                        "collate": "utf8_general_ci"
                    },{
                        "name": "nextround"
                    }
                ],
                users =[{
                        "databases":[{ "name":"sampledb"}],
                        "name":"demouser",
                        "password": "demopassword"
                    }
                ])
            assert_equal(instance.status, "BUILD")
            return instance
        self.instances = self.clients.do("create_instance",
            "/instances", "POST", 200, "OK",
            create_instance,
            (["json_rack_instance"], ["xml_rack_instance"]))
        #self.instance_j = create_instance(self.clients.json,
        #                                  "json_rack_instance")
        #self.instance_x = create_instance(self.clients.xml,
        #                                  "xml_rack_instance")

    @test(depends_on=[post_create_instance])
    def wait_for_instances(self):
        for instance in self.instances:
            while instance.status != "ACTIVE":
                assert_equal(instance.status, "BUILD")
                instance.get()
                time.sleep(0.1)
        global json_instance
        json_instance = self.instances[0]
        global xml_instance
        xml_instance = self.instances[1]


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Databases(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def post_create_databases(self):
        self.clients.do("create_databases",
            ("/instances/%s/databases" % json_instance.id,
             "/instances/%s/databases" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id : client.databases.create(id, databases=[
                {
                    "name": "testingdb",
                    "character_set": "utf8",
                    "collate": "utf8_general_ci"
                },
                {
                    "name": "anotherdb"
                },
                    {
                    "name": "oneMoreDB"
                }
            ]), ([json_instance.id], [xml_instance.id]))

    @test(depends_on=[post_create_databases])
    def get_list_databases(self):
        results = self.clients.do("list_databases",
            ("/instances/%s/databases" % json_instance.id,
             "/instances/%s/databases" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id : client.databases.list(id),
            ([json_instance.id], [xml_instance.id]))

    @test(depends_on=[post_create_databases])
    def get_list_databases_limit_two(self):
        results = self.clients.do("list_databases_pagination",
            ("/instances/%s/databases?limit=1" % json_instance.id,
             "/instances/%s/databases?limit=2" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id, limit : client.databases.list(id, limit=limit),
            ([json_instance.id, 1], [xml_instance.id, 2]))
        assert_equal(1, len(results[JSON_INDEX]))
        assert_equal(2, len(results[XML_INDEX]))
        assert_equal("anotherdb", results[JSON_INDEX].next)
        assert_equal("nextround", results[XML_INDEX].next)

    @test(depends_on=[post_create_databases],
          runs_after=[get_list_databases, get_list_databases_limit_two])
    def delete_databases(self):
        results = self.clients.do("delete_databases",
            ("/instances/%s/databases/testingdb" % json_instance.id,
             "/instances/%s/databases/oneMoreDB" % xml_instance.id),
            "DELETE", 202, "Accepted",
            lambda client, id, name : client.databases.delete(id, name),
            ([json_instance.id, 'testingdb'], [xml_instance.id, 'oneMoreDB']))



@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Users(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def post_create_users(self):
        results = self.clients.do("create_users",
            ("/instances/%s/users" % json_instance.id,
             "/instances/%s/users" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id : client.users.create(id, [
                {
                    "name": "dbuser1",
                    "password": "password",
                    "database": "databaseA"
                    },
                {
                    "name": "dbuser2",
                    "password": "password",
                    "databases": [
                        {
                            "name": "databaseB"
                            },
                        {
                            "name": "databaseC"
                            }
                        ]
                    },
                {
                    "name": "dbuser3",
                    "password": "password",
                    "database": "databaseD"
                    }
                ]),
            ([json_instance.id], [xml_instance.id]))

    @test(depends_on=[post_create_users])
    def get_list_users(self):
        results = self.clients.do("list_users",
            ("/instances/%s/users" % json_instance.id,
             "/instances/%s/users" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id : client.users.list(id),
            ([json_instance.id], [xml_instance.id]))

    @test(depends_on=[post_create_users])
    def get_list_users_limit_two(self):
        results = self.clients.do("list_users_pagination",
            ("/instances/%s/users?limit=2" % json_instance.id,
             "/instances/%s/users?limit=2" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id : client.users.list(id, limit=2),
            ([json_instance.id], [xml_instance.id]))

    @test(depends_on=[post_create_users],
          runs_after=[get_list_users, get_list_users_limit_two])
    def delete_users(self):
        user_name = "testuser"
        results = self.clients.do("delete_users",
            ("/instances/%s/users/%s" % (json_instance.id, user_name),
             "/instances/%s/users/%s" % (xml_instance.id, user_name)),
            "DELETE", 202, "Accepted",
            lambda client, id : client.users.delete(id, user=user_name),
            ([json_instance.id], [xml_instance.id]))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Root(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def post_enable_root_access(self):
        results = self.clients.do("enable_root_user",
            ("/instances/%s/root" % json_instance.id,
             "/instances/%s/root" % xml_instance.id),
            "POST", 200, "OK",
            lambda client, id : client.root.create(id),
            ([json_instance.id], [xml_instance.id]))

    @test(depends_on=[post_enable_root_access])
    def get_check_root_access(self):
        results = self.clients.do("check_root_user",
            ("/instances/%s/root" % json_instance.id,
             "/instances/%s/root" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id : client.root.is_root_enabled(id),
            ([json_instance.id], [xml_instance.id]))
        assert_equal(results[JSON_INDEX], True)
        assert_equal(results[XML_INDEX], True)


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class InstanceList(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def get_list_instance_index(self):
        results = self.clients.do("instances_index",
            "/instances", "GET", 200, "OK",
            lambda client : client.instances.list())
        for result in results:
            assert_equal(2, len(result))

    @test
    def get_instance_details(self):
        results = self.clients.do("instance_status_detail",
            ("/instances/%s" % json_instance.id,
             "/instances/%s" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id : client.instances.get(id),
            ([json_instance.id], [xml_instance.id]))
        assert_equal(results[JSON_INDEX].id, json_instance.id)
        assert_equal(results[XML_INDEX].id, xml_instance.id)

    @test
    def get_list_instance_index_limit_two(self):
        third_instance = self.clients.json.instances.create(
            "The Third Instance", 1, volume={'size':2})
        while third_instance.status != "ACTIVE":
            third_instance.get()
            time.sleep(0.1)

        results = self.clients.do("instances_index_pagination",
            "/instances?limit=2", "GET", 200, "OK",
            lambda client : client.instances.list(limit=2))
        for result in results:
            assert_equal(2, len(result))

        self.clients.json.instances.delete(third_instance.id)


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Actions(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    def _wait_for_active(self, *acceptable_states):
        for instance in (json_instance, xml_instance):
            instance.get()
            print('instance.status=%s' % instance.status)
            while instance.status != "ACTIVE":
                assert_true(instance.status in acceptable_states,
                    "Instance status == %s; expected it to be one of these: %s"
                    % (instance.status, acceptable_states))
                instance.get()
                time.sleep(0.1)

    @test
    def instance_restart(self):
        results = self.clients.do("instance_restart",
            ("/instances/%s/action" % json_instance.id,
             "/instances/%s/action" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id : client.instances.restart(id),
            ([json_instance.id], [xml_instance.id]))
        self._wait_for_active("RESTART")

    @test
    def instance_resize_volume(self):
        results = self.clients.do("instance_resize_volume",
            ("/instances/%s/action" % json_instance.id,
             "/instances/%s/action" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id : client.instances.resize_volume(id, 4),
            ([json_instance.id], [xml_instance.id]))
        self._wait_for_active("RESIZE")
        assert_equal(json_instance.volume['size'], 4)
        assert_equal(xml_instance.volume['size'], '4')

    @test
    def instance_resize_flavor(self):
        results = self.clients.do("instance_resize_flavor",
            ("/instances/%s/action" % json_instance.id,
             "/instances/%s/action" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id : client.instances.resize_flavor(id, 3),
            ([json_instance.id], [xml_instance.id]))
        self._wait_for_active("RESIZE")
        assert_equal(json_instance.flavor['id'], '3')
        assert_equal(xml_instance.flavor['id'], '3')


@test(depends_on=[CreateInstance], groups=['uses_instances', "MgmtHosts"])
class MgmtHosts(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def mgmt_list_hosts(self):
        results = self.clients.do("mgmt_list_hosts",
            "/mgmt/hosts", "GET", 200, "OK",
            lambda client : client.mgmt.hosts.index())
        with Check() as check:
            for hosts in results:
                check.equal(1, len(hosts))
                check.equal("fake_host", hosts[0].name)
            check.equal(2, results[0][0].instanceCount)
            # In XML land this is a string. :'(
            check.equal("2", results[1][0].instanceCount)

    @test
    def mgmt_get_host_detail(self):
        results = self.clients.do("mgmt_get_host_detail",
            "/mgmt/hosts/fake_host", "GET", 200, "OK",
            lambda client : client.mgmt.hosts.get("fake_host"))
        with Check() as check:
            for host in results:
                check.equal(results[0].name, "fake_host")
                check.equal(results[1].name, "fake_host")
                # XML entries won't come back as these types. :(
                check.true(isinstance(results[0].percentUsed, int)),
                check.true(isinstance(results[0].totalRAM, int)),
                check.true(isinstance(results[0].usedRAM, int)),
        with Check() as check:
            for host in results:
                check.equal(2, len(host.instances))
                for instance in host.instances:
                    check.equal(instance['status'], 'ACTIVE')
                    check.true(instance['name'] == 'json_rack_instance' or
                               instance['name'] == 'xml_rack_instance')
                    #TODO: Check with GUID regex.
                    check.true(isinstance(instance['id'], six.string_types))
                    check.true(isinstance(instance['server_id'],
                                          six.string_types))
                    check.true(isinstance(instance['tenant_id'],
                                          six.string_types))

    @test
    def mgmt_host_update_all(self):
        results = self.clients.do("mgmt_host_update",
            "/mgmt/hosts/fake_host/instances/action",
            "POST", 202, "Accepted",
            lambda client : client.mgmt.hosts.update_all("fake_host"))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtStorage(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def mgmt_get_storage(self):
        results = self.clients.do("mgmt_get_storage",
            "/mgmt/storage", "GET", 200, "OK",
            lambda client : client.mgmt.storage.index())
        for index, devices in enumerate(results):
            with Check() as check:
                check.equal(1, len(devices))
                device = devices[0]
                check.equal(int(device.capacity['available']), 90)
                check.equal(int(device.capacity['total']), 100)
                check.equal(device.name, "fake_storage")
                check.equal(int(device.provision['available']), 40)
                check.equal(int(device.provision['percent']), 10)
                check.equal(int(device.provision['total']), 50)
                check.equal(device.type, "test_type")
                check.equal(int(device.used), 10)
                if index == JSON_INDEX:
                    check.true(isinstance(device.capacity['available'], int))
                    check.true(isinstance(device.capacity['total'], int))
                    check.true(isinstance(device.provision['available'], int))
                    check.true(isinstance(device.provision['percent'], int))
                    check.true(isinstance(device.provision['total'], int))
                    check.true(isinstance(device.used, int))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtAccount(object):

    @before_class
    def setup(self):
        self.clients = ClientPair()

    @test
    def mgmt_get_account_details(self):
        results = self.clients.do("mgmt_get_account_details",
            "/mgmt/accounts/admin", "GET", 200, "OK",
            lambda client : client.mgmt.accounts.show("admin"))
        with Check() as check:
            for account_info in results:
                check.equal(2, len(account_info.instances))
                check.equal('admin', account_info.id)

    @test
    def mgmt_get_account_list(self):
        results = self.clients.do("mgmt_list_accounts",
            "/mgmt/accounts", "GET", 200, "OK",
            lambda client : client.mgmt.accounts.index())
        for index, result in enumerate(results):
            for account in result.accounts:
                assert_equal('admin', account['id'])
                if index == JSON_INDEX:
                    assert_equal(2, account['num_instances'])
                else:
                    assert_equal("2", account['num_instances'])


def for_both(func):
    def both(self):
        for result in self.results:
            func(self, result)
    return both


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstance(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()
        self.results = self.clients.do("mgmt_get_instance_details",
            ("/mgmt/instances/%s" % json_instance.id,
             "/mgmt/instances/%s" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id : client.mgmt.instances.show(id),
            ([json_instance.id], [xml_instance.id]))

    @test
    @for_both
    def created(self, result):
        #TODO: use regex
        assert_true(isinstance(result.created, six.string_types))

    @test
    def deleted(self):
        assert_equal(self.results[JSON_INDEX].deleted, False)
        assert_equal(self.results[XML_INDEX].deleted, "False")

    @test
    @for_both
    def flavor(self, result):
        assert_true(result.flavor['id'] == "1" or result.flavor['id'] == "3")
        assert_equal(len(result.flavor['links']), 2)
        #TODO: validate the flavors format.

    @test
    @for_both
    def guest_status(self, result):
        assert_equal(result.guest_status['state_description'], 'running')

    @test
    @for_both
    def host(self, result):
        assert_equal(result.host, 'fake_host')

    @test
    def id(self):
        assert_equal(self.results[JSON_INDEX].id, json_instance.id)
        assert_equal(self.results[XML_INDEX].id, xml_instance.id)

    @test
    @for_both
    def links(self, result):
        assert_true(isinstance(result.links, list))
        for link in result.links:
            assert_true(isinstance(link, dict))
            assert_true(isinstance(link['href'], six.string_types))
            assert_true(isinstance(link['rel'], six.string_types))

    @test
    def local_id(self):
        #TODO: regex
        assert_true(isinstance(self.results[JSON_INDEX].local_id, int))
        assert_true(isinstance(self.results[XML_INDEX].local_id,
                               six.string_types))

    @test
    @for_both
    def name(self, result):
        #TODO: regex
        assert_true(isinstance(result.name,
                               six.string_types))

    @test
    @for_both
    def server_id(self, result):
        #TODO: regex
        assert_true(isinstance(result.server_id,
                               six.string_types))

    @test
    @for_both
    def status(self, result):
        #TODO: regex
        assert_equal("ACTIVE", result.status)

    @test
    @for_both
    def task_description(self, result):
        assert_equal(result.task_description, "No tasks for the instance.")

    @test
    @for_both
    def tenant_id(self, result):
        assert_equal(result.tenant_id, "admin")

    @test
    @for_both
    def updated(self, result):
        #TODO: regex
        assert_true(isinstance(result.updated,
                               six.string_types))

    @test
    @for_both
    def volume(self, result):
        #TODO: regex
        assert_true(isinstance(result.volume, dict))
        assert_true('id' in result.volume)
        assert_true('size' in result.volume)


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstanceIndex(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def mgmt_instance_index(self, deleted=False):
        url = "/mgmt/instances?deleted=false"
        results = self.clients.do("mgmt_instance_index",
            "/mgmt/instances?deleted=false", "GET", 200, "OK",
            lambda client : client.mgmt.instances.index(deleted=False))
        #TODO: Valdiate everything... *sigh*


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstanceDiagnostics(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def mgmt_get_instance_diagnostics(self):
        results = self.clients.do("mgmt_instance_diagnostics",
            ("/mgmt/instances/%s/diagnostics" % json_instance.id,
             "/mgmt/instances/%s/diagnostics" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id: client.diagnostics.get(id),
            ([json_instance.id], [xml_instance.id]))
        #TODO: validate the actual stuff that comes back (booorring!).


@test(depends_on=[CreateInstance])
class MgmtInstanceRoot(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def mgmt_get_root_details(self):
        results = self.clients.do("mgmt_get_root_details",
            ("/mgmt/instances/%s/root" % json_instance.id,
             "/mgmt/instances/%s/root" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id: client.mgmt.instances.root_enabled_history(id),
            ([json_instance.id], [xml_instance.id]))
        #TODO: validate the actual stuff that comes back (booorring!).


@test(depends_on=[CreateInstance])
class MgmtInstanceHWInfo(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def mgmt_get_hw_info(self):
        results = self.clients.do("mgmt_get_hw_info",
            ("/mgmt/instances/%s/hwinfo" % json_instance.id,
             "/mgmt/instances/%s/hwinfo" % xml_instance.id),
            "GET", 200, "OK",
            lambda client, id: client.hw_info.get(id),
            ([json_instance.id], [xml_instance.id]))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstanceReboot(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def mgmt_instance_reboot(self):
        results = self.clients.do("instance_reboot",
            ("/mgmt/instances/%s/action" % json_instance.id,
             "/mgmt/instances/%s/action" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id: client.mgmt.instances.reboot(id),
            ([json_instance.id], [xml_instance.id]))


@test(depends_on=[CreateInstance],
      groups=['uses_instances'], enabled=False)
class MgmtInstanceGuestUpdate(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def mgmt_instance_guest_update(self):
        results = self.clients.do("guest_update",
            ("/mgmt/instances/%s/action" % json_instance.id,
             "/mgmt/instances/%s/action" % xml_instance.id),
            "POST", 202, "Accepted",
            lambda client, id: client.mgmt.instances.update(id),
            ([json_instance.id], [xml_instance.id]))


@test(depends_on=[CreateInstance], runs_after_groups=['uses_instances'])
class ZzzDeleteInstance(object):

    @before_class
    def mgmt_get_instance_details(self):
        self.clients = ClientPair()

    @test
    def zzz_delete_instance(self):
        results = self.clients.do("delete_instance",
            ("/instances/%s" % json_instance.id,
             "/instances/%s" % xml_instance.id),
            "DELETE", 202, "Accepted",
            lambda client, id: client.instances.delete(id),
            ([json_instance.id], [xml_instance.id]))
        for result in json_instance, xml_instance:
            result.get()
            assert_equal(result.status, "SHUTDOWN")


if __name__ == "__main__":
    TestProgram().run_and_exit()
