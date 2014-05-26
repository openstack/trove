#    Copyright 2011 OpenStack Foundation
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

from troveclient.compat.exceptions import Unauthorized

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_raises

from trove import tests
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.admin"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class TestAdminRequired(object):
    """
    These tests verify that admin privileges are checked
    when calling management level functions.
    """

    @before_class
    def setUp(self):
        """Create the user and client for use in the subsequent tests."""
        self.user = test_config.users.find_user(Requirements(is_admin=False))
        self.dbaas = create_dbaas_client(self.user)

    @test
    def test_accounts_show(self):
        """A regular user may not view the details of any account."""
        assert_raises(Unauthorized, self.dbaas.accounts.show, 0)

    @test
    def test_hosts_index(self):
        """A regular user may not view the list of hosts."""
        assert_raises(Unauthorized, self.dbaas.hosts.index)

    @test
    def test_hosts_get(self):
        """A regular user may not view the details of any host."""
        assert_raises(Unauthorized, self.dbaas.hosts.get, 0)

    @test
    def test_mgmt_show(self):
        """
        A regular user may not view the management details
        of any instance.
        """
        assert_raises(Unauthorized, self.dbaas.management.show, 0)

    @test
    def test_mgmt_root_history(self):
        """
        A regular user may not view the root access history of
        any instance.
        """
        assert_raises(Unauthorized,
                      self.dbaas.management.root_enabled_history, 0)

    @test
    def test_mgmt_instance_reboot(self):
        """A regular user may not perform an instance reboot."""
        assert_raises(Unauthorized, self.dbaas.management.reboot, 0)

    @test
    def test_mgmt_instance_reset_task_status(self):
        """A regular user may not perform an instance task status reset."""
        assert_raises(Unauthorized, self.dbaas.management.reset_task_status, 0)

    @test
    def test_storage_index(self):
        """A regular user may not view the list of storage available."""
        assert_raises(Unauthorized, self.dbaas.storage.index)

    @test
    def test_diagnostics_get(self):
        """A regular user may not view the diagnostics."""
        assert_raises(Unauthorized, self.dbaas.diagnostics.get, 0)

    @test
    def test_hwinfo_get(self):
        """A regular user may not view the hardware info."""
        assert_raises(Unauthorized, self.dbaas.hwinfo.get, 0)
