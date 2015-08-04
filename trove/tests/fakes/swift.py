# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
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

from hashlib import md5
from mock import MagicMock, patch
import httplib
import json
import os
import socket
import swiftclient
import swiftclient.client as swift_client
import uuid

from oslo_log import log as logging
from swiftclient import client as swift

from trove.common.i18n import _  # noqa

LOG = logging.getLogger(__name__)


class FakeSwiftClient(object):
    """Logs calls instead of executing."""
    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def Connection(self, *args, **kargs):
        LOG.debug("fake FakeSwiftClient Connection")
        return FakeSwiftConnection()


class FakeSwiftConnection(object):
    """Logging calls instead of executing."""
    MANIFEST_HEADER_KEY = 'X-Object-Manifest'
    url = 'http://mockswift/v1'

    def __init__(self, *args, **kwargs):
        self.manifest_prefix = None
        self.manifest_name = None
        self.container_objects = {}

    def get_auth(self):
        return (
            u"http://127.0.0.1:8080/v1/AUTH_c7b038976df24d96bf1980f5da17bd89",
            u'MIINrwYJKoZIhvcNAQcCoIINoDCCDZwCAQExCTAHBgUrDgMCGjCCDIgGCSqGSIb3'
            u'DQEHAaCCDHkEggx1eyJhY2Nlc3MiOiB7InRva2VuIjogeyJpc3N1ZWRfYXQiOiAi'
            u'MjAxMy0wMy0xOFQxODoxMzoyMC41OTMyNzYiLCAiZXhwaXJlcyI6ICIyMDEzLTAz'
            u'LTE5VDE4OjEzOjIwWiIsICJpZCI6ICJwbGFjZWhvbGRlciIsICJ0ZW5hbnQiOiB7'
            u'ImVuYWJsZWQiOiB0cnVlLCAiZGVzY3JpcHRpb24iOiBudWxsLCAibmFtZSI6ICJy'
            u'ZWRkd2FyZiIsICJpZCI6ICJjN2IwMzg5NzZkZjI0ZDk2YmYxOTgwZjVkYTE3YmQ4'
            u'OSJ9fSwgInNlcnZpY2VDYXRhbG9nIjogW3siZW5kcG9pbnRzIjogW3siYWRtaW5')

    def get_account(self):
        return ({'content-length': '2', 'accept-ranges': 'bytes',
                 'x-timestamp': '1363049003.92304',
                 'x-trans-id': 'tx9e5da02c49ed496395008309c8032a53',
                 'date': 'Tue, 10 Mar 2013 00:43:23 GMT',
                 'x-account-bytes-used': '0',
                 'x-account-container-count': '0',
                 'content-type': 'application/json; charset=utf-8',
                 'x-account-object-count': '0'}, [])

    def head_container(self, container):
        LOG.debug("fake head_container(%s)" % container)
        if container == 'missing_container':
            raise swift.ClientException('fake exception',
                                        http_status=httplib.NOT_FOUND)
        elif container == 'unauthorized_container':
            raise swift.ClientException('fake exception',
                                        http_status=httplib.UNAUTHORIZED)
        elif container == 'socket_error_on_head':
            raise socket.error(111, 'ECONNREFUSED')
        pass

    def put_container(self, container):
        LOG.debug("fake put_container(%s)" % container)
        pass

    def get_container(self, container, **kwargs):
        LOG.debug("fake get_container(%s)" % container)
        fake_header = None
        fake_body = [{'name': 'backup_001'},
                     {'name': 'backup_002'},
                     {'name': 'backup_003'}]
        return fake_header, fake_body

    def head_object(self, container, name):
        LOG.debug("fake put_container(%(container)s, %(name)s)" %
                  {'container': container, 'name': name})
        checksum = md5()
        if self.manifest_prefix and self.manifest_name == name:
            for object_name in sorted(self.container_objects.iterkeys()):
                object_checksum = md5(self.container_objects[object_name])
                # The manifest file etag for a HEAD or GET is the checksum of
                # the concatenated checksums.
                checksum.update(object_checksum.hexdigest())
            # this is included to test bad swift segment etags
            if name.startswith("bad_manifest_etag_"):
                return {'etag': '"this_is_an_intentional_bad_manifest_etag"'}
        else:
            if name in self.container_objects:
                checksum.update(self.container_objects[name])
            else:
                return {'etag': 'fake-md5-sum'}

        # Currently a swift HEAD object returns etag with double quotes
        return {'etag': '"%s"' % checksum.hexdigest()}

    def get_object(self, container, name, resp_chunk_size=None):
        LOG.debug("fake get_object(%(container)s, %(name)s)" %
                  {'container': container, 'name': name})
        if container == 'socket_error_on_get':
            raise socket.error(111, 'ECONNREFUSED')
        if 'metadata' in name:
            fake_object_header = None
            metadata = {}
            if container == 'unsupported_version':
                metadata['version'] = '9.9.9'
            else:
                metadata['version'] = '1.0.0'
            metadata['backup_id'] = 123
            metadata['volume_id'] = 123
            metadata['backup_name'] = 'fake backup'
            metadata['backup_description'] = 'fake backup description'
            metadata['created_at'] = '2013-02-19 11:20:54,805'
            metadata['objects'] = [{
                'backup_001': {'compression': 'zlib', 'length': 10},
                'backup_002': {'compression': 'zlib', 'length': 10},
                'backup_003': {'compression': 'zlib', 'length': 10}
            }]
            metadata_json = json.dumps(metadata, sort_keys=True, indent=2)
            fake_object_body = metadata_json
            return (fake_object_header, fake_object_body)

        fake_header = {'etag': '"fake-md5-sum"'}
        if resp_chunk_size:
            def _object_info():
                length = 0
                while length < (1024 * 1024):
                    yield os.urandom(resp_chunk_size)
                    length += resp_chunk_size
            fake_object_body = _object_info()
        else:
            fake_object_body = os.urandom(1024 * 1024)
        return (fake_header, fake_object_body)

    def put_object(self, container, name, contents, **kwargs):
        LOG.debug("fake put_object(%(container)s, %(name)s)" %
                  {'container': container, 'name': name})
        if container == 'socket_error_on_put':
            raise socket.error(111, 'ECONNREFUSED')
        headers = kwargs.get('headers', {})
        object_checksum = md5()
        if self.MANIFEST_HEADER_KEY in headers:
            # the manifest prefix format is <container>/<prefix> where
            # container is where the object segments are in and prefix is the
            # common prefix for all segments.
            self.manifest_prefix = headers.get(self.MANIFEST_HEADER_KEY)
            self.manifest_name = name
            object_checksum.update(contents)
        else:
            if hasattr(contents, 'read'):
                chunk_size = 128
                object_content = ""
                chunk = contents.read(chunk_size)
                while chunk:
                    object_content += chunk
                    object_checksum.update(chunk)
                    chunk = contents.read(chunk_size)

                self.container_objects[name] = object_content
            else:
                object_checksum.update(contents)
                self.container_objects[name] = contents

            # this is included to test bad swift segment etags
            if name.startswith("bad_segment_etag_"):
                return "this_is_an_intentional_bad_segment_etag"
        return object_checksum.hexdigest()

    def post_object(self, container, name, headers={}):
        LOG.debug("fake post_object(%(container)s, %(name)s, %(head)s)" %
                  {'container': container, 'name': name, 'head': str(headers)})

    def delete_object(self, container, name):
        LOG.debug("fake delete_object(%(container)s, %(name)s)" %
                  {'container': container, 'name': name})
        if container == 'socket_error_on_delete':
            raise socket.error(111, 'ECONNREFUSED')
        pass


class Patcher(object):
    """Objects that need to mock global symbols throughout their existence
    should extend this base class.
    The object acts as a context manager which, when used in conjunction with
    the 'with' statement, terminates all running patchers when it leaves the
    scope.
    """

    def __init__(self):
        self.__patchers = None

    def __enter__(self):
        self.__patchers = []
        return self

    def __exit__(self, type, value, traceback):
        # Stop patchers in the LIFO order.
        while self.__patchers:
            self.__patchers.pop().stop()

    def _start_patcher(self, patcher):
        """All patchers started by this method will be automatically
        terminated on __exit__().
        """
        self.__patchers.append(patcher)
        return patcher.start()


class SwiftClientStub(Patcher):
    """
    Component for controlling behavior of Swift Client Stub.  Instantiated
    before tests are invoked in "fake" mode.  Invoke methods to control
    behavior so that systems under test can interact with this as it is a
    real swift client with a real backend

    example:

    if FAKE:
        swift_stub = SwiftClientStub()
        swift_stub.with_account('xyz')

    # returns swift account info and auth token
    component_using_swift.get_swift_account()

    if FAKE:
        swift_stub.with_container('test-container-name')

    # returns swift container information - mostly faked
    component_using.swift.create_container('test-container-name')
    component_using_swift.get_container_info('test-container-name')

    if FAKE:
        swift_stub.with_object('test-container-name', 'test-object-name',
            'test-object-contents')

    # returns swift object info and contents
    component_using_swift.create_object('test-container-name',
        'test-object-name', 'test-contents')
    component_using_swift.get_object('test-container-name', 'test-object-name')

    if FAKE:
        swift_stub.without_object('test-container-name', 'test-object-name')

    # allows object to be removed ONCE
    component_using_swift.remove_object('test-container-name',
        'test-object-name')
    # throws ClientException - 404
    component_using_swift.get_object('test-container-name', 'test-object-name')
    component_using_swift.remove_object('test-container-name',
        'test-object-name')

    if FAKE:
        swift_stub.without_object('test-container-name', 'test-object-name')

    # allows container to be removed ONCE
    component_using_swift.remove_container('test-container-name')
    # throws ClientException - 404
    component_using_swift.get_container('test-container-name')
    component_using_swift.remove_container('test-container-name')
    """

    def __init__(self):
        super(SwiftClientStub, self).__init__()
        self._connection = swift_client.Connection()
        self._containers = {}
        self._containers_list = []
        self._objects = {}

    def _remove_object(self, name, some_list):
        idx = [i for i, obj in enumerate(some_list) if obj['name'] == name]
        if len(idx) == 1:
            del some_list[idx[0]]

    def _ensure_object_exists(self, container, name):
        self._connection.get_object(container, name)

    def with_account(self, account_id):
        """
        setups up account headers

        example:

        if FAKE:
            swift_stub = SwiftClientStub()
            swift_stub.with_account('xyz')

        # returns swift account info and auth token
        component_using_swift.get_swift_account()

        :param account_id: account id
        """

        def account_resp():
            return ({'content-length': '2', 'accept-ranges': 'bytes',
                     'x-timestamp': '1363049003.92304',
                     'x-trans-id': 'tx9e5da02c49ed496395008309c8032a53',
                     'date': 'Tue, 10 Mar 2013 00:43:23 GMT',
                     'x-account-bytes-used': '0',
                     'x-account-container-count': '0',
                     'content-type': 'application/json; charset=utf-8',
                     'x-account-object-count': '0'}, self._containers_list)

        get_auth_return_value = (
            u"http://127.0.0.1:8080/v1/AUTH_c7b038976df24d96bf1980f5da17bd89",
            u'MIINrwYJKoZIhvcNAQcCoIINoDCCDZwCAQExCTAHBgUrDgMCGjCCDIgGCSqGSIb3'
            u'DQEHAaCCDHkEggx1eyJhY2Nlc3MiOiB7InRva2VuIjogeyJpc3N1ZWRfYXQiOiAi'
            u'MjAxMy0wMy0xOFQxODoxMzoyMC41OTMyNzYiLCAiZXhwaXJlcyI6ICIyMDEzLTAz'
            u'LTE5VDE4OjEzOjIwWiIsICJpZCI6ICJwbGFjZWhvbGRlciIsICJ0ZW5hbnQiOiB7'
            u'ImVuYWJsZWQiOiB0cnVlLCAiZGVzY3JpcHRpb24iOiBudWxsLCAibmFtZSI6ICJy'
            u'ZWRkd2FyZiIsICJpZCI6ICJjN2IwMzg5NzZkZjI0ZDk2YmYxOTgwZjVkYTE3YmQ4'
            u'OSJ9fSwgInNlcnZpY2VDYXRhbG9nIjogW3siZW5kcG9pbnRzIjogW3siYWRtaW5')

        get_auth_patcher = patch.object(
            swift_client.Connection, 'get_auth',
            MagicMock(return_value=get_auth_return_value))
        self._start_patcher(get_auth_patcher)

        get_account_patcher = patch.object(
            swift_client.Connection, 'get_account',
            MagicMock(return_value=account_resp()))
        self._start_patcher(get_account_patcher)

        return self

    def _create_container(self, container_name):
        container = {'count': 0, 'bytes': 0, 'name': container_name}
        self._containers[container_name] = container
        self._containers_list.append(container)
        self._objects[container_name] = []

    def _ensure_container_exists(self, container):
        self._connection.get_container(container)

    def _delete_container(self, container):
        self._remove_object(container, self._containers_list)
        del self._containers[container]
        del self._objects[container]

    def with_container(self, container_name):
        """
        sets expectations for creating a container and subsequently getting its
        information

        example:

        if FAKE:
            swift_stub.with_container('test-container-name')

        # returns swift container information - mostly faked
        component_using.swift.create_container('test-container-name')
        component_using_swift.get_container_info('test-container-name')

        :param container_name: container name that is expected to be created
        """

        def container_resp(container):
            return ({'content-length': '2', 'x-container-object-count': '0',
                     'accept-ranges': 'bytes', 'x-container-bytes-used': '0',
                     'x-timestamp': '1363370869.72356',
                     'x-trans-id': 'tx7731801ac6ec4e5f8f7da61cde46bed7',
                     'date': 'Fri, 10 Mar 2013 18:07:58 GMT',
                     'content-type': 'application/json; charset=utf-8'},
                    self._objects[container])

        # if this is called multiple times then nothing happens
        put_container_patcher = patch.object(swift_client.Connection,
                                             'put_container')
        self._start_patcher(put_container_patcher)

        def side_effect_func(*args, **kwargs):
            if args[0] in self._containers:
                return container_resp(args[0])
            else:
                raise swiftclient.ClientException('Resource Not Found',
                                                  http_status=404)

        self._create_container(container_name)
        # return container headers
        get_container_patcher = patch.object(
            swift_client.Connection, 'get_container',
            MagicMock(side_effect=side_effect_func))
        self._start_patcher(get_container_patcher)

        return self

    def without_container(self, container):
        """
        sets expectations for removing a container and subsequently throwing an
        exception for further interactions

        example:

        if FAKE:
            swift_stub.without_container('test-container-name')

        # returns swift container information - mostly faked
        component_using.swift.remove_container('test-container-name')
        # throws exception "Resource Not Found - 404"
        component_using_swift.get_container_info('test-container-name')

        :param container: container name that is expected to be removed
        """
        # first ensure container
        self._ensure_container_exists(container)
        self._delete_container(container)
        return self

    def with_object(self, container, name, contents):
        """
        sets expectations for creating an object and subsequently getting its
        contents

        example:

        if FAKE:
        swift_stub.with_object('test-container-name', 'test-object-name',
            'test-object-contents')

        # returns swift object info and contents
        component_using_swift.create_object('test-container-name',
            'test-object-name', 'test-contents')
        component_using_swift.get_object('test-container-name',
            'test-object-name')

        :param container: container name that is the object belongs
        :param name: the name of the object expected to be created
        :param contents: the contents of the object
        """

        put_object_patcher = patch.object(
            swift_client.Connection, 'put_object',
            MagicMock(return_value=uuid.uuid1()))
        self._start_patcher(put_object_patcher)

        def side_effect_func(*args, **kwargs):
            if (args[0] in self._containers and
                args[1] in map(lambda x: x['name'],
                               self._objects[args[0]])):
                return (
                    {'content-length': len(contents), 'accept-ranges': 'bytes',
                     'last-modified': 'Mon, 10 Mar 2013 01:06:34 GMT',
                     'etag': 'eb15a6874ce265e2c3eb1b4891567bab',
                     'x-timestamp': '1363568794.67584',
                     'x-trans-id': 'txef3aaf26c897420c8e77c9750ce6a501',
                     'date': 'Mon, 10 Mar 2013 05:35:14 GMT',
                     'content-type': 'application/octet-stream'},
                    [obj for obj in self._objects[args[0]]
                     if obj['name'] == args[1]][0]['contents'])
            else:
                raise swiftclient.ClientException('Resource Not Found',
                                                  http_status=404)

        get_object_patcher = patch.object(
            swift_client.Connection, 'get_object',
            MagicMock(side_effect=side_effect_func))
        self._start_patcher(get_object_patcher)

        self._remove_object(name, self._objects[container])
        self._objects[container].append(
            {'bytes': 13, 'last_modified': '2013-03-15T22:10:49.361950',
             'hash': 'ccc55aefbf92aa66f42b638802c5e7f6', 'name': name,
             'content_type': 'application/octet-stream', 'contents': contents})
        return self

    def without_object(self, container, name):
        """
        sets expectations for deleting an object

        example:

        if FAKE:
        swift_stub.without_object('test-container-name', 'test-object-name')

        # allows container to be removed ONCE
        component_using_swift.remove_container('test-container-name')
        # throws ClientException - 404
        component_using_swift.get_container('test-container-name')
        component_using_swift.remove_container('test-container-name')

        :param container: container name that is the object belongs
        :param name: the name of the object expected to be removed
        """
        self._ensure_container_exists(container)
        self._ensure_object_exists(container, name)

        def side_effect_func(*args, **kwargs):
            if not [obj for obj in self._objects[args[0]]
                    if obj['name'] == [args[1]]]:
                raise swiftclient.ClientException('Resource Not found',
                                                  http_status=404)
            else:
                return None

        delete_object_patcher = patch.object(
            swift_client.Connection, 'delete_object',
            MagicMock(side_effect=side_effect_func))
        self._start_patcher(delete_object_patcher)

        self._remove_object(name, self._objects[container])
        return self


def fake_create_swift_client(calculate_etag=False, *args):
    return FakeSwiftClient.Connection(*args)
