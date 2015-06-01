# Copyright 2014 IBM Corp.
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

from mock import MagicMock
from mock import patch

from trove.cmd import common as common_cmd
from trove.cmd import conductor as conductor_cmd
import trove.common.cfg as cfg
from trove.openstack.common import service as os_service
import trove.tests.fakes.conf as fake_conf
from trove.tests.unittests import trove_testtools

CONF = cfg.CONF
TROVE_UT = 'trove.tests.unittests'


def mocked_conf(manager):
    return fake_conf.FakeConf({
        'conductor_queue': 'conductor',
        'conductor_manager': manager,
        'trove_conductor_workers': 1,
        'host': 'mockhost',
        'report_interval': 1})


class NoopManager(object):
    RPC_API_VERSION = 1.0


class ConductorConfTests(trove_testtools.TestCase):
    def setUp(self):
        super(ConductorConfTests, self).setUp()

    def tearDown(self):
        super(ConductorConfTests, self).tearDown()

    def _test_manager(self, conf, rt_mgr_name):
        def mock_launch(server, workers):
            qualified_mgr = "%s.%s" % (server.manager_impl.__module__,
                                       server.manager_impl.__class__.__name__)
            self.assertEqual(rt_mgr_name, qualified_mgr, "Invalid manager")
            return MagicMock()

        os_service.launch = mock_launch
        with patch.object(common_cmd, 'initialize',
                          MagicMock(return_value=conf)):
            conductor_cmd.main()

    def test_user_defined_manager(self):
        qualified_mgr = TROVE_UT + ".conductor.test_conf.NoopManager"
        self._test_manager(mocked_conf(qualified_mgr), qualified_mgr)

    def test_default_manager(self):
        qualified_mgr = "trove.conductor.manager.Manager"
        self._test_manager(CONF, qualified_mgr)

    def test_invalid_manager(self):
        self.assertRaises(ImportError, self._test_manager,
                          mocked_conf('foo.bar.MissingMgr'),
                          'foo.bar.MissingMgr')
