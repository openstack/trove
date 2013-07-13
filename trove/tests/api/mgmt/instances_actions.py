#    Copyright 2013 OpenStack Foundation
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
from trove.common.context import TroveContext
from trove.instance.tasks import InstanceTasks
from trove.instance import models as imodels
from trove.instance.models import DBInstance
from trove.extensions.mgmt.instances.models import MgmtInstance

from novaclient.v1_1.servers import Server

from proboscis import test
from proboscis import before_class
from proboscis import after_class
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from trove.common import exception
from trove.extensions.mgmt.instances.service import MgmtInstanceController

GROUP = "dbaas.api.mgmt.action.reset-task-status"


class MgmtInstanceBase(object):

    def setUp(self):
        self.mock = mox.Mox()
        self._create_instance()
        self.controller = MgmtInstanceController()

    def tearDown(self):
        self.db_info.delete()

    def _create_instance(self):
        self.context = TroveContext(is_admin=True)
        self.tenant_id = 999
        self.db_info = DBInstance.create(
            name="instance",
            flavor_id=1,
            tenant_id=self.tenant_id,
            volume_size=None,
            service_type='mysql',
            task_status=InstanceTasks.NONE)
        self.server = self.mock.CreateMock(Server)
        self.instance = imodels.Instance(self.context,
                                         self.db_info,
                                         self.server,
                                         service_status="ACTIVE")

    def _make_request(self, path='/', context=None, **kwargs):
        from webob import Request
        path = '/'
        print("path: %s" % path)
        return Request.blank(path=path, environ={'trove.context': context},
                             **kwargs)

    def _reload_db_info(self):
        self.db_info = DBInstance.find_by(id=self.db_info.id, deleted=False)


@test(groups=[GROUP])
class RestartTaskStatusTests(MgmtInstanceBase):
    @before_class
    def setUp(self):
        super(RestartTaskStatusTests, self).setUp()

    @after_class
    def tearDown(self):
        super(RestartTaskStatusTests, self).tearDown()

    def _change_task_status_to(self, new_task_status):
        self.db_info.task_status = new_task_status
        self.db_info.save()

    def _make_request(self, path='/', context=None, **kwargs):
        req = super(RestartTaskStatusTests, self)._make_request(path, context,
                                                                **kwargs)
        req.method = 'POST'
        body = {'reset-task-status': {}}
        return req, body

    def reset_task_status(self):
        self.mock.StubOutWithMock(MgmtInstance, 'load')
        MgmtInstance.load(context=self.context,
                          id=self.db_info.id).AndReturn(self.instance)
        self.mock.ReplayAll()

        req, body = self._make_request(context=self.context)
        self.controller = MgmtInstanceController()
        resp = self.controller.action(req, body, self.tenant_id,
                                      self.db_info.id)

        self.mock.UnsetStubs()
        self.mock.VerifyAll()
        return resp

    @test
    def mgmt_restart_task_requires_admin_account(self):
        context = TroveContext(is_admin=False)
        req, body = self._make_request(context=context)
        self.controller = MgmtInstanceController()
        assert_raises(exception.Forbidden, self.controller.action,
                      req, body, self.tenant_id, self.db_info.id)

    @test
    def mgmt_restart_task_returns_json(self):
        resp = self.reset_task_status()
        out = resp.data("application/json")
        assert_equal(out, None)

    @test
    def mgmt_restart_task_returns_xml(self):
        resp = self.reset_task_status()
        out = resp.data("application/xml")
        assert_equal(out, None)

    @test
    def mgmt_restart_task_changes_status_to_none(self):
        self._change_task_status_to(InstanceTasks.BUILDING)
        self.reset_task_status()
        self._reload_db_info()
        assert_equal(self.db_info.task_status, InstanceTasks.NONE)
