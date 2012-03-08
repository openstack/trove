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

from reddwarf import tests
from reddwarf.common import config
from reddwarf.common import wsgi
from reddwarf.database import models
from reddwarf.database import service
from reddwarf.tests import unit


LOG = logging.getLogger(__name__)


class ControllerTestBase(tests.BaseTest):

    def setUp(self):
        super(ControllerTestBase, self).setUp()
        conf, reddwarf_app = config.Config.load_paste_app('reddwarfapp',
                {"config_file": tests.test_config_file()}, None)
        self.app = unit.TestApp(reddwarf_app)


class DummyApp(wsgi.Router):

    def __init__(self, controller):
        mapper = routes.Mapper()
        mapper.resource("resource", "/resources",
                                controller=controller.create_resource())
        super(DummyApp, self).__init__(mapper)


class TestInstanceController(ControllerTestBase):

    DUMMY_INSTANCE_ID = "123"

    def setUp(self):
        self.instances_path = "/tenant/instances"
        super(TestInstanceController, self).setUp()

    def test_show(self):
        # block = factory_models.IpBlockFactory()
        instance = mox.MockAnything()
        self.mock.StubOutWithMock(models.Instance, 'data')
        models.Instance.data().AndReturn({"id": self.DUMMY_INSTANCE_ID,
                                   "name": "DUMMY_NAME",
                                   "status": "BUILD"})
        self.mock.StubOutWithMock(models.Instance, '__init__')
        models.Instance.__init__(context=mox.IgnoreArg(), uuid=mox.IgnoreArg())
        self.mock.ReplayAll()

        response = self.app.get("%s/%s" % (self.instances_path,
                                           self.DUMMY_INSTANCE_ID),
                                           headers={'X-Auth-Token': '123'})

        self.assertEqual(response.status_int, 201)
