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
from trove.common import cfg

from proboscis import before_class
from proboscis import after_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true

from trove import tests
from trove.tests.api.users import TestUsers
from trove.tests.api.instances import instance_info
from trove.tests import util
from trove.tests.api.databases import TestMysqlAccess

CONF = cfg.CONF
GROUP = "dbaas.api.root.oncreate"


@test(depends_on_classes=[TestMysqlAccess],
      runs_after=[TestUsers],
      groups=[tests.DBAAS_API, GROUP, tests.INSTANCES])
class TestRootOnCreate(object):
    """
    Test 'CONF.root_on_create', which if True, creates the root user upon
    database instance initialization.
    """

    root_enabled_timestamp = 'Never'

    @before_class
    def setUp(self):
        self.orig_conf_value = CONF.root_on_create
        CONF.root_on_create = True
        self.dbaas = util.create_dbaas_client(instance_info.user)
        self.dbaas_admin = util.create_dbaas_client(instance_info.admin_user)
        self.history = self.dbaas_admin.management.root_enabled_history
        self.enabled = self.dbaas.root.is_root_enabled

    @after_class
    def tearDown(self):
        CONF.root_on_create = self.orig_conf_value

    @test
    def test_root_on_create(self):
        """Test that root is enabled after instance creation"""
        enabled = self.enabled(instance_info.id).rootEnabled
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(enabled)

    @test(depends_on=[test_root_on_create])
    def test_history_after_root_on_create(self):
        """Test that the timestamp in the root enabled history is set"""
        self.root_enabled_timestamp = self.history(instance_info.id).enabled
        assert_equal(200, self.dbaas.last_http_code)
        assert_not_equal(self.root_enabled_timestamp, 'Never')

    @test(depends_on=[test_history_after_root_on_create])
    def test_reset_root(self):
        """Test that root reset does not alter the timestamp"""
        orig_timestamp = self.root_enabled_timestamp
        self.dbaas.root.create(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        self.root_enabled_timestamp = self.history(instance_info.id).enabled
        assert_equal(200, self.dbaas.last_http_code)
        assert_equal(orig_timestamp, self.root_enabled_timestamp)

    @test(depends_on=[test_reset_root])
    def test_root_still_enabled(self):
        """Test that after root was reset, it's still enabled."""
        enabled = self.enabled(instance_info.id).rootEnabled
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(enabled)
