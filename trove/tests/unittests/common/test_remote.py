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

from mock import MagicMock
import testtools
from testtools import matchers

import swiftclient.client

from trove.tests.fakes.swift import SwiftClientStub
from trove.common.context import TroveContext
from trove.common import remote
from trove.common import exception
from trove.common import cfg


class TestRemote(testtools.TestCase):
    def setUp(self):
        super(TestRemote, self).setUp()

    def tearDown(self):
        super(TestRemote, self).tearDown()

    def test_creation(self):
        swiftclient.client.Connection.get_auth = MagicMock(return_value=None)
        conn = swiftclient.client.Connection()
        self.assertIsNone(conn.get_auth())

    def test_create_swift_client(self):
        mock_resp = MagicMock()
        swiftclient.client.Connection.get_container = MagicMock(
            return_value=["text", mock_resp])
        service_catalog = [{'endpoints': [{'publicURL': 'example.com'}],
                            'type': 'object-store'}]
        client = remote.create_swift_client(TroveContext(
            tenant='123',
            service_catalog=service_catalog))
        headers, container = client.get_container('bob')
        self.assertIs(headers, "text")
        self.assertIs(container, mock_resp)

    def test_empty_account(self):
        """
        this is an account with no containers and no objects
        """
        # setup expectation
        swift_stub = SwiftClientStub()
        swift_stub.with_account('123223')
        # interact
        conn = swiftclient.client.Connection()
        account_info = conn.get_account()
        self.assertThat(account_info, matchers.Not(matchers.Is(None)))
        self.assertThat(len(account_info), matchers.Is(2))
        self.assertThat(account_info, matchers.IsInstance(tuple))
        self.assertThat(account_info[0], matchers.IsInstance(dict))
        self.assertThat(account_info[0],
                        matchers.KeysEqual('content-length', 'accept-ranges',
                                           'x-timestamp', 'x-trans-id', 'date',
                                           'x-account-bytes-used',
                                           'x-account-container-count',
                                           'content-type',
                                           'x-account-object-count'))
        self.assertThat(account_info[1], matchers.IsInstance(list))
        self.assertThat(len(account_info[1]), matchers.Is(0))

    def test_one_container(self):
        """
        tests to ensure behavior is normal with one container
        """
        # setup expectation
        swift_stub = SwiftClientStub()
        swift_stub.with_account('123223')
        cont_name = 'a-container-name'
        swift_stub.with_container(cont_name)
        # interact
        conn = swiftclient.client.Connection()
        conn.get_auth()
        conn.put_container(cont_name)
        # get headers plus container metadata
        self.assertThat(len(conn.get_account()), matchers.Is(2))
        # verify container details
        account_containers = conn.get_account()[1]
        self.assertThat(len(account_containers), matchers.Is(1))
        self.assertThat(account_containers[0],
                        matchers.KeysEqual('count', 'bytes', 'name'))
        self.assertThat(account_containers[0]['name'], matchers.Is(cont_name))
        # get container details
        cont_info = conn.get_container(cont_name)
        self.assertIsNotNone(cont_info)
        self.assertThat(cont_info[0], matchers.KeysEqual('content-length',
                        'x-container-object-count', 'accept-ranges',
                        'x-container-bytes-used', 'x-timestamp',
                        'x-trans-id', 'date', 'content-type'))
        self.assertThat(len(cont_info[1]), matchers.Equals(0))
        # remove container
        swift_stub.without_container(cont_name)
        with testtools.ExpectedException(swiftclient.ClientException):
            conn.get_container(cont_name)
            # ensure there are no more containers in account
        self.assertThat(len(conn.get_account()[1]), matchers.Is(0))

    def test_one_object(self):
        swift_stub = SwiftClientStub()
        swift_stub.with_account('123223')
        swift_stub.with_container('bob')
        swift_stub.with_object('bob', 'test', 'test_contents')
        # create connection
        conn = swiftclient.client.Connection()
        # test container lightly
        cont_info = conn.get_container('bob')
        self.assertIsNotNone(cont_info)
        self.assertThat(cont_info[0],
                        matchers.KeysEqual('content-length',
                                           'x-container-object-count',
                                           'accept-ranges',
                                           'x-container-bytes-used',
                                           'x-timestamp', 'x-trans-id', 'date',
                                           'content-type'))
        cont_objects = cont_info[1]
        self.assertThat(len(cont_objects), matchers.Equals(1))
        obj_1 = cont_objects[0]
        self.assertThat(obj_1, matchers.Equals(
            {'bytes': 13, 'last_modified': '2013-03-15T22:10:49.361950',
             'hash': 'ccc55aefbf92aa66f42b638802c5e7f6', 'name': 'test',
             'content_type': 'application/octet-stream',
             'contents': 'test_contents'}))
        # test object api - not much to do here
        self.assertThat(conn.get_object('bob', 'test')[1],
                        matchers.Is('test_contents'))

        # test remove object
        swift_stub.without_object('bob', 'test')
        # interact
        with testtools.ExpectedException(swiftclient.ClientException):
            conn.delete_object('bob', 'test')
        self.assertThat(len(conn.get_container('bob')[1]), matchers.Is(0))

    def test_two_objects(self):
        swift_stub = SwiftClientStub()
        swift_stub.with_account('123223')
        swift_stub.with_container('bob')
        swift_stub.with_container('bob2')
        swift_stub.with_object('bob', 'test', 'test_contents')
        swift_stub.with_object('bob', 'test2', 'test_contents2')

        conn = swiftclient.client.Connection()

        self.assertIs(len(conn.get_account()), 2)
        cont_info = conn.get_container('bob')
        self.assertIsNotNone(cont_info)
        self.assertThat(cont_info[0],
                        matchers.KeysEqual('content-length',
                                           'x-container-object-count',
                                           'accept-ranges',
                                           'x-container-bytes-used',
                                           'x-timestamp', 'x-trans-id', 'date',
                                           'content-type'))
        self.assertThat(len(cont_info[1]), matchers.Equals(2))
        self.assertThat(cont_info[1][0], matchers.Equals(
            {'bytes': 13, 'last_modified': '2013-03-15T22:10:49.361950',
             'hash': 'ccc55aefbf92aa66f42b638802c5e7f6', 'name': 'test',
             'content_type': 'application/octet-stream',
             'contents': 'test_contents'}))
        self.assertThat(conn.get_object('bob', 'test')[1],
                        matchers.Is('test_contents'))
        self.assertThat(conn.get_object('bob', 'test2')[1],
                        matchers.Is('test_contents2'))

        swift_stub.without_object('bob', 'test')
        with testtools.ExpectedException(swiftclient.ClientException):
            conn.delete_object('bob', 'test')
        self.assertThat(len(conn.get_container('bob')[1]), matchers.Is(1))

        swift_stub.without_container('bob')
        with testtools.ExpectedException(swiftclient.ClientException):
            conn.get_container('bob')

        self.assertThat(len(conn.get_account()), matchers.Is(2))

    def test_nonexisting_container(self):
        """
        when a container does not exist and is accessed then a 404 is returned
        """
        from trove.tests.fakes.swift import SwiftClientStub

        swift_stub = SwiftClientStub()
        swift_stub.with_account('123223')
        swift_stub.with_container('existing')

        conn = swiftclient.client.Connection()

        with testtools.ExpectedException(swiftclient.ClientException):
            conn.get_container('nonexisting')

    def test_replace_object(self):
        """
        Test to ensure that if an object is updated the container object
        count is the same and the contents of the object are updated
        """
        swift_stub = SwiftClientStub()
        swift_stub.with_account('1223df2')
        swift_stub.with_container('new-container')
        swift_stub.with_object('new-container', 'new-object',
                               'new-object-contents')

        conn = swiftclient.client.Connection()

        conn.put_object('new-container', 'new-object', 'new-object-contents')
        obj_resp = conn.get_object('new-container', 'new-object')
        self.assertThat(obj_resp, matchers.Not(matchers.Is(None)))
        self.assertThat(len(obj_resp), matchers.Is(2))
        self.assertThat(obj_resp[1], matchers.Is('new-object-contents'))

        # set expected behavior - trivial here since it is the intended
        # behavior however keep in mind this is just to support testing of
        # trove components
        swift_stub.with_object('new-container', 'new-object',
                               'updated-object-contents')

        conn.put_object('new-container', 'new-object',
                        'updated-object-contents')
        obj_resp = conn.get_object('new-container', 'new-object')
        self.assertThat(obj_resp, matchers.Not(matchers.Is(None)))
        self.assertThat(len(obj_resp), matchers.Is(2))
        self.assertThat(obj_resp[1], matchers.Is('updated-object-contents'))
        # ensure object count has not increased
        self.assertThat(len(conn.get_container('new-container')[1]),
                        matchers.Is(1))


class TestCreateCinderClient(testtools.TestCase):
    def setUp(self):
        super(TestCreateCinderClient, self).setUp()
        self.volumev2_public_url = 'http://publicURL/v2'
        self.volume_public_url_region_two = 'http://publicURL-r2/v1'
        self.service_catalog = [
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': self.volumev2_public_url,
                    }
                ],
                'type': 'volumev2'
            },
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': 'http://publicURL-r1/v1',
                    },
                    {
                        'region': 'RegionTwo',
                        'publicURL': self.volume_public_url_region_two,
                    }
                ],
                'type': 'volume'
            }
        ]

    def tearDown(self):
        super(TestCreateCinderClient, self).tearDown()
        cfg.CONF.clear_override('cinder_url')
        cfg.CONF.clear_override('cinder_service_type')
        cfg.CONF.clear_override('os_region_name')

    def test_create_with_no_conf_no_catalog(self):
        self.assertRaises(exception.EmptyCatalog,
                          remote.create_cinder_client,
                          TroveContext())

    def test_create_with_conf_override(self):
        cinder_url_from_conf = 'http://example.com'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('cinder_url', cinder_url_from_conf)

        client = remote.create_cinder_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s/%s' % (cinder_url_from_conf, tenant_from_ctx),
                         client.client.management_url)

    def test_create_with_conf_override_trailing_slash(self):
        cinder_url_from_conf = 'http://example.com/'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('cinder_url', cinder_url_from_conf)
        client = remote.create_cinder_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s%s' % (cinder_url_from_conf, tenant_from_ctx),
                         client.client.management_url)

    def test_create_with_catalog_and_default_service_type(self):
        client = remote.create_cinder_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.volumev2_public_url,
                         client.client.management_url)

    def test_create_with_catalog_all_opts(self):
        cfg.CONF.set_override('cinder_service_type', 'volume')
        cfg.CONF.set_override('os_region_name', 'RegionTwo')
        client = remote.create_cinder_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.volume_public_url_region_two,
                         client.client.management_url)


class TestCreateNovaClient(testtools.TestCase):
    def setUp(self):
        super(TestCreateNovaClient, self).setUp()
        self.compute_public_url = 'http://publicURL/v2'
        self.computev3_public_url_region_two = 'http://publicURL-r2/v3'
        self.service_catalog = [
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': self.compute_public_url,
                    }
                ],
                'type': 'compute'
            },
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': 'http://publicURL-r1/v1',
                    },
                    {
                        'region': 'RegionTwo',
                        'publicURL': self.computev3_public_url_region_two,
                    }
                ],
                'type': 'computev3'
            }
        ]

    def tearDown(self):
        super(TestCreateNovaClient, self).tearDown()
        cfg.CONF.clear_override('nova_compute_url')
        cfg.CONF.clear_override('nova_compute_service_type')
        cfg.CONF.clear_override('os_region_name')

    def test_create_with_no_conf_no_catalog(self):
        self.assertRaises(exception.EmptyCatalog,
                          remote.create_nova_client,
                          TroveContext())

    def test_create_with_conf_override(self):
        nova_url_from_conf = 'http://example.com'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('nova_compute_url', nova_url_from_conf)

        client = remote.create_nova_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s/%s' % (nova_url_from_conf, tenant_from_ctx),
                         client.client.management_url)

    def test_create_with_conf_override_trailing_slash(self):
        nova_url_from_conf = 'http://example.com/'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('nova_compute_url', nova_url_from_conf)
        client = remote.create_nova_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s%s' % (nova_url_from_conf, tenant_from_ctx),
                         client.client.management_url)

    def test_create_with_catalog_and_default_service_type(self):
        client = remote.create_nova_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.compute_public_url,
                         client.client.management_url)

    def test_create_with_catalog_all_opts(self):
        cfg.CONF.set_override('nova_compute_service_type', 'computev3')
        cfg.CONF.set_override('os_region_name', 'RegionTwo')
        client = remote.create_nova_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.computev3_public_url_region_two,
                         client.client.management_url)


class TestCreateHeatClient(testtools.TestCase):
    def setUp(self):
        super(TestCreateHeatClient, self).setUp()
        self.heat_public_url = 'http://publicURL/v2'
        self.heatv3_public_url_region_two = 'http://publicURL-r2/v3'
        self.service_catalog = [
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': self.heat_public_url,
                    }
                ],
                'type': 'orchestration'
            },
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': 'http://publicURL-r1/v1',
                    },
                    {
                        'region': 'RegionTwo',
                        'publicURL': self.heatv3_public_url_region_two,
                    }
                ],
                'type': 'orchestrationv3'
            }
        ]

    def tearDown(self):
        super(TestCreateHeatClient, self).tearDown()
        cfg.CONF.clear_override('heat_url')
        cfg.CONF.clear_override('heat_service_type')
        cfg.CONF.clear_override('os_region_name')

    def test_create_with_no_conf_no_catalog(self):
        self.assertRaises(exception.EmptyCatalog,
                          remote.create_heat_client,
                          TroveContext())

    def test_create_with_conf_override(self):
        heat_url_from_conf = 'http://example.com'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('heat_url', heat_url_from_conf)

        client = remote.create_heat_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s/%s' % (heat_url_from_conf, tenant_from_ctx),
                         client.http_client.endpoint)

    def test_create_with_conf_override_trailing_slash(self):
        heat_url_from_conf = 'http://example.com/'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('heat_url', heat_url_from_conf)
        client = remote.create_heat_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s%s' % (heat_url_from_conf, tenant_from_ctx),
                         client.http_client.endpoint)

    def test_create_with_catalog_and_default_service_type(self):
        client = remote.create_heat_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.heat_public_url,
                         client.http_client.endpoint)

    def test_create_with_catalog_all_opts(self):
        cfg.CONF.set_override('heat_service_type', 'orchestrationv3')
        cfg.CONF.set_override('os_region_name', 'RegionTwo')
        client = remote.create_heat_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.heatv3_public_url_region_two,
                         client.http_client.endpoint)


class TestCreateSwiftClient(testtools.TestCase):
    def setUp(self):
        super(TestCreateSwiftClient, self).setUp()
        self.swift_public_url = 'http://publicURL/v2'
        self.swiftv3_public_url_region_two = 'http://publicURL-r2/v3'
        self.service_catalog = [
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': self.swift_public_url,
                    }
                ],
                'type': 'object-store'
            },
            {
                'endpoints': [
                    {
                        'region': 'RegionOne',
                        'publicURL': 'http://publicURL-r1/v1',
                    },
                    {
                        'region': 'RegionTwo',
                        'publicURL': self.swiftv3_public_url_region_two,
                    }
                ],
                'type': 'object-storev3'
            }
        ]

    def tearDown(self):
        super(TestCreateSwiftClient, self).tearDown()
        cfg.CONF.clear_override('swift_url')
        cfg.CONF.clear_override('swift_service_type')
        cfg.CONF.clear_override('os_region_name')

    def test_create_with_no_conf_no_catalog(self):
        self.assertRaises(exception.EmptyCatalog,
                          remote.create_swift_client,
                          TroveContext())

    def test_create_with_conf_override(self):
        swift_url_from_conf = 'http://example.com/AUTH_'
        tenant_from_ctx = 'abc'
        cfg.CONF.set_override('swift_url', swift_url_from_conf)

        client = remote.create_swift_client(
            TroveContext(tenant=tenant_from_ctx))
        self.assertEqual('%s%s' % (swift_url_from_conf, tenant_from_ctx),
                         client.url)

    def test_create_with_catalog_and_default_service_type(self):
        client = remote.create_swift_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.swift_public_url,
                         client.url)

    def test_create_with_catalog_all_opts(self):
        cfg.CONF.set_override('swift_service_type', 'object-storev3')
        cfg.CONF.set_override('os_region_name', 'RegionTwo')
        client = remote.create_swift_client(
            TroveContext(service_catalog=self.service_catalog))
        self.assertEqual(self.swiftv3_public_url_region_two,
                         client.url)


class TestEndpoints(testtools.TestCase):
    """
    Copied from glance/tests/unit/test_auth.py.
    """
    def setUp(self):
        super(TestEndpoints, self).setUp()

        self.service_catalog = [
            {
                'endpoint_links': [],
                'endpoints': [
                    {
                        'adminURL': 'http://localhost:8080/',
                        'region': 'RegionOne',
                        'internalURL': 'http://internalURL/',
                        'publicURL': 'http://publicURL/',
                    },
                    {
                        'adminURL': 'http://localhost:8081/',
                        'region': 'RegionTwo',
                        'internalURL': 'http://internalURL2/',
                        'publicURL': 'http://publicURL2/',
                    },
                ],
                'type': 'object-store',
                'name': 'Object Storage Service',
            }
        ]

    def test_get_endpoint_empty_catalog(self):
        self.assertRaises(exception.EmptyCatalog,
                          remote.get_endpoint,
                          None)

    def test_get_endpoint_with_custom_server_type(self):
        endpoint = remote.get_endpoint(self.service_catalog,
                                       service_type='object-store',
                                       endpoint_region='RegionOne')
        self.assertEqual('http://publicURL/', endpoint)

    def test_get_endpoint_with_custom_endpoint_type(self):
        endpoint = remote.get_endpoint(self.service_catalog,
                                       service_type='object-store',
                                       endpoint_type='internalURL',
                                       endpoint_region='RegionOne')
        self.assertEqual('http://internalURL/', endpoint)

    def test_get_endpoint_raises_with_ambiguous_endpoint_region(self):
        self.assertRaises(exception.RegionAmbiguity,
                          remote.get_endpoint,
                          self.service_catalog,
                          service_type='object-store')

    def test_get_endpoint_raises_with_invalid_service_type(self):
        self.assertRaises(exception.NoServiceEndpoint,
                          remote.get_endpoint,
                          self.service_catalog,
                          service_type='foo')

    def test_get_endpoint_raises_with_invalid_endpoint_type(self):
        self.assertRaises(exception.NoServiceEndpoint,
                          remote.get_endpoint,
                          self.service_catalog,
                          service_type='object-store',
                          endpoint_type='foo',
                          endpoint_region='RegionOne')

    def test_get_endpoint_raises_with_invalid_endpoint_region(self):
        self.assertRaises(exception.NoServiceEndpoint,
                          remote.get_endpoint,
                          self.service_catalog,
                          service_type='object-store',
                          endpoint_region='foo',
                          endpoint_type='internalURL')

    def test_get_endpoint_ignores_missing_type(self):
        service_catalog = [
            {
                'name': 'Other Service',
            },
            {
                'endpoint_links': [],
                'endpoints': [
                    {
                        'adminURL': 'http://localhost:8080/',
                        'region': 'RegionOne',
                        'internalURL': 'http://internalURL/',
                        'publicURL': 'http://publicURL/',
                    },
                    {
                        'adminURL': 'http://localhost:8081/',
                        'region': 'RegionTwo',
                        'internalURL': 'http://internalURL2/',
                        'publicURL': 'http://publicURL2/',
                    },
                ],
                'type': 'object-store',
                'name': 'Object Storage Service',
            }
        ]
        endpoint = remote.get_endpoint(service_catalog,
                                       service_type='object-store',
                                       endpoint_region='RegionOne')
        self.assertEqual('http://publicURL/', endpoint)
