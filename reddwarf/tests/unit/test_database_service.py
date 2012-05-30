# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright 2011 OpenStack LLC.
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

import mox
import logging
from nose import SkipTest
import novaclient

from reddwarf import tests
from reddwarf.common import config
from reddwarf.common import utils
from reddwarf.instance import models
from reddwarf.tests import unit


LOG = logging.getLogger(__name__)


class ControllerTestBase(tests.BaseTest):

    def setUp(self):
        super(ControllerTestBase, self).setUp()
        conf, reddwarf_app = config.Config.load_paste_app('reddwarfapp',
                {"config_file": tests.test_config_file()}, None)
        self.app = unit.TestApp(reddwarf_app)


class TestInstanceController(ControllerTestBase):

    DUMMY_INSTANCE_ID = "123"
    DUMMY_INSTANCE = {"id": DUMMY_INSTANCE_ID,
    "name": "DUMMY_NAME",
    "status": "BUILD",
    "created": "createtime",
    "updated": "updatedtime",
    "flavor": {},
    "links": [],
    "addresses": {}}

    def setUp(self):
        self.instances_path = "/tenant/instances"
        super(TestInstanceController, self).setUp()

    # TODO(hub-cap): Start testing the failure cases
    def test_show_broken(self):
        raise SkipTest()
        response = self.app.get("%s/%s" % (self.instances_path,
                                           self.DUMMY_INSTANCE_ID),
                                headers={'X-Auth-Token': '123'})
        self.assertEqual(response.status_int, 404)

    def test_show(self):
        raise SkipTest()
        self.mock.StubOutWithMock(models.Instance, 'data')
        models.Instance.data().AndReturn(self.DUMMY_INSTANCE)
        self.mock.StubOutWithMock(models.Instance, '__init__')
        models.Instance.__init__(context=mox.IgnoreArg(), uuid=mox.IgnoreArg())
        self.mock.ReplayAll()

        response = self.app.get("%s/%s" % (self.instances_path,
                                           self.DUMMY_INSTANCE_ID),
                                           headers={'X-Auth-Token': '123'})

        self.assertEqual(response.status_int, 201)

    def test_index(self):
        raise SkipTest()
        self.mock.StubOutWithMock(models.Instances, 'data')
        models.Instances.data().AndReturn([self.DUMMY_INSTANCE])
        self.mock.StubOutWithMock(models.Instances, '__init__')
        models.Instances.__init__(mox.IgnoreArg())
        self.mock.ReplayAll()
        response = self.app.get("%s" % (self.instances_path),
                                           headers={'X-Auth-Token': '123'})
        self.assertEqual(response.status_int, 201)

    def mock_out_client_create(self):
        """Stubs out a fake server returned from novaclient.
           This is akin to calling Client.servers.get(uuid)
           and getting the server object back."""
        self.FAKE_SERVER = self.mock.CreateMock(object)
        self.FAKE_SERVER.name = 'my_name'
        self.FAKE_SERVER.status = 'ACTIVE'
        self.FAKE_SERVER.updated = utils.utcnow()
        self.FAKE_SERVER.created = utils.utcnow()
        self.FAKE_SERVER.id = utils.generate_uuid()
        self.FAKE_SERVER.flavor = 'http://localhost/1234/flavors/1234'
        self.FAKE_SERVER.links = [{
                    "href": "http://localhost/1234/instances/123",
                    "rel": "self"
                },
                {
                    "href": "http://localhost/1234/instances/123",
                    "rel": "bookmark"
                }]
        self.FAKE_SERVER.addresses = {
                "private": [
                    {
                        "addr": "10.0.0.4",
                        "version": 4
                    }
                ]
            }

        client = self.mock.CreateMock(novaclient.v1_1.Client)
        servers = self.mock.CreateMock(novaclient.v1_1.servers.ServerManager)
        servers.create(mox.IgnoreArg(),
                       mox.IgnoreArg(),
                       mox.IgnoreArg()).AndReturn(self.FAKE_SERVER)
        client.servers = servers
        self.mock.StubOutWithMock(models.NovaRemoteModelBase, 'get_client')
        models.NovaRemoteModelBase.get_client(mox.IgnoreArg()). \
            AndReturn(client)

    def test_create(self):
        raise SkipTest()
        self.mock.StubOutWithMock(models.Instance, 'data')
        models.Instance.data().AndReturn(self.DUMMY_INSTANCE)

        self.mock.StubOutWithMock(models.ServiceImage, 'find_by')
        models.ServiceImage.find_by(service_name=mox.IgnoreArg()).AndReturn(
                {'image_id': 1234})

        self.mock_out_client_create()
        self.mock.ReplayAll()

        body = {
            "instance": {
                "databases": [
                    {
                        "character_set": "utf8",
                        "collate": "utf8_general_ci",
                        "name": "sampledb"
                    },
                    {
                        "name": "nextround"
                    }
                ],
                "flavorRef": "http://localhost/v1.0/tenant/flavors/1",
                "name": "json_rack_instance",
            }
        }
        response = self.app.post_json("%s" % (self.instances_path), body=body,
                                           headers={'X-Auth-Token': '123'},
                                           )
        print(response)
        self.assertEqual(response.status_int, 201)
