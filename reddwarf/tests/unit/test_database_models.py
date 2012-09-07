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
import novaclient

from reddwarf import tests
from reddwarf.common import utils
from reddwarf.common import exception
from reddwarf.instance import models
from reddwarf.instance.tasks import InstanceTasks
from reddwarf.tests.factories import models as factory_models


class TestInstance(tests.BaseTest):

    FAKE_SERVER = None

    def setUp(self):
        super(TestInstance, self).setUp()
        self.expected_name = 'my_name'
        self.expected_id = utils.generate_uuid()

    def mock_out_client(self):
        """Stubs out a fake server returned from novaclient.
           This is akin to calling Client.servers.get(uuid)
           and getting the server object back."""
        self.FAKE_SERVER = self.mock.CreateMock(object)
        self.FAKE_SERVER.name = self.expected_name
        self.FAKE_SERVER.status = 'ACTIVE'
        self.FAKE_SERVER.updated = utils.utcnow()
        self.FAKE_SERVER.created = utils.utcnow()
        self.FAKE_SERVER.id = self.expected_id
        self.FAKE_SERVER.flavor = ('http://localhost/1234/flavors/',
                                   '52415800-8b69-11e0-9b19-734f1195ff37')
        self.FAKE_SERVER.links = [
            {
                "href": "http://localhost/1234/instances/123",
                "rel": "self",
            },
            {
                "href": "http://localhost/1234/instances/123",
                "rel": "bookmark",
            },
        ]
        self.FAKE_SERVER.addresses = {
            "private": [
                {
                    "addr": "10.0.0.4",
                    "version": 4
                },
            ],
        }

        client = self.mock.CreateMock(novaclient.v1_1.Client)
        servers = self.mock.CreateMock(novaclient.v1_1.servers.ServerManager)
        servers.get(mox.IgnoreArg()).AndReturn(self.FAKE_SERVER)
        client.servers = servers
        self.mock.StubOutWithMock(models.NovaRemoteModelBase, 'get_client')
        models.NovaRemoteModelBase.get_client(mox.IgnoreArg()). \
            AndReturn(client)
        self.mock.ReplayAll()

    def test_create_dbinstance_data(self):
        """This ensures the data() call in a new
           DBInstance object returns the proper mapped data
           to a dict from attr's"""
        # Creates the instance via __init__
        from reddwarf.instance import tasks
        instance = factory_models.DBInstance(
            task_status=InstanceTasks.BUILDING,
            name=self.expected_name,
            compute_instance_id=self.expected_id,
            task_start_time=None).data()

        self.assertEqual(instance['name'], self.expected_name)
        self.assertEqual(instance['compute_instance_id'], self.expected_id)
        self.assertEqual(instance['task_id'], InstanceTasks.BUILDING.code)
        self.assertEqual(instance['task_description'],
                         InstanceTasks.BUILDING.db_text)

    def test_create_instance_data_without_flavorref(self):
        #todo(cp16net) fix this to work with the factory
        self.mock_out_client()
        self.FAKE_SERVER.flavor = None
        self.assertRaises(exception.BadRequest, factory_models.Instance())
