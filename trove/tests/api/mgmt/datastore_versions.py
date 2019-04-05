# Copyright [2015] Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis import before_class
from proboscis.check import Check
from proboscis import test
from troveclient.compat import exceptions

from trove.tests.config import CONFIG
from trove.tests.util import create_client
from trove.tests.util import create_dbaas_client
from trove.tests.util import create_glance_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.ds_versions"


@test(groups=[GROUP])
def mgmt_datastore_version_list_requires_admin_account():
    """Verify that an admin context is required to call this function."""
    client = create_client(is_admin=False)
    assert_raises(exceptions.Unauthorized, client.mgmt_datastore_versions.list)


@test(groups=[GROUP])
class MgmtDataStoreVersion(object):
    """Tests the mgmt datastore version methods."""

    @before_class
    def setUp(self):
        """Create client for tests."""
        reqs = Requirements(is_admin=True)
        self.user = CONFIG.users.find_user(reqs)
        self.client = create_dbaas_client(self.user)
        self.images = []
        if test_config.glance_client is not None:
            glance_user = test_config.users.find_user(
                Requirements(services=["glance"]))
            self.glance_client = create_glance_client(glance_user)
            images = self.glance_client.images.list()
            for image in images:
                self.images.append(image.id)

    def _find_ds_version_by_name(self, ds_version_name):
        ds_versions = self.client.mgmt_datastore_versions.list()
        for ds_version in ds_versions:
            if ds_version_name == ds_version.name:
                return ds_version

    @test
    def test_mgmt_ds_version_list_original_count(self):
        """Tests the mgmt datastore version list method."""
        self.ds_versions = self.client.mgmt_datastore_versions.list()
        # datastore-versions should exist for a functional Trove deployment.
        assert_true(len(self.ds_versions) > 0)

    @test(depends_on=[test_mgmt_ds_version_list_original_count])
    def test_mgmt_ds_version_list_fields_present(self):
        """Verify that all expected fields are returned by list method."""

        expected_fields = [
            'id',
            'name',
            'datastore_id',
            'datastore_name',
            'datastore_manager',
            'image',
            'packages',
            'active',
            'default',
        ]

        for ds_version in self.ds_versions:
            with Check() as check:
                for field in expected_fields:
                    check.true(hasattr(ds_version, field),
                               "List lacks field %s." % field)

    @test(depends_on=[test_mgmt_ds_version_list_original_count])
    def test_mgmt_ds_version_get(self):
        """Tests the mgmt datastore version get method."""
        test_version = self.ds_versions[0]
        found_ds_version = self.client.mgmt_datastore_versions.get(
            test_version.id)
        assert_equal(test_version.name, found_ds_version.name)
        assert_equal(test_version.datastore_id, found_ds_version.datastore_id)
        assert_equal(test_version.datastore_name,
                     found_ds_version.datastore_name)
        assert_equal(test_version.datastore_manager,
                     found_ds_version.datastore_manager)
        assert_equal(test_version.image, found_ds_version.image)
        assert_equal(test_version.packages, found_ds_version.packages)
        assert_equal(test_version.active, found_ds_version.active)
        assert_equal(test_version.default, found_ds_version.default)

    @test(depends_on=[test_mgmt_ds_version_list_original_count])
    def test_mgmt_ds_version_create(self):
        """Tests the mgmt datastore version create method."""
        response = self.client.mgmt_datastore_versions.create(
            'test_version1', 'test_ds', 'test_mgr',
            self.images[0], ['vertica-7.1'])
        assert_equal(None, response)
        assert_equal(202, self.client.last_http_code)

        # Since we created one more ds_version
        # lets check count of total ds_versions, it should be increased by 1
        new_ds_versions = self.client.mgmt_datastore_versions.list()
        assert_equal(len(self.ds_versions) + 1,
                     len(new_ds_versions))

        # Match the contents of newly created ds_version.
        self.created_version = self._find_ds_version_by_name('test_version1')
        assert_equal('test_version1', self.created_version.name)
        assert_equal('test_ds', self.created_version.datastore_name)
        assert_equal('test_mgr', self.created_version.datastore_manager)
        assert_equal(self.images[0], self.created_version.image)
        assert_equal(['vertica-7.1'], self.created_version.packages)
        assert_true(self.created_version.active)
        assert_false(self.created_version.default)

    @test(depends_on=[test_mgmt_ds_version_create])
    def test_mgmt_ds_version_patch(self):
        """Tests the mgmt datastore version edit method."""
        self.client.mgmt_datastore_versions.edit(
            self.created_version.id, image=self.images[1],
            packages=['pkg1'])
        assert_equal(202, self.client.last_http_code)

        # Lets match the content of patched datastore
        patched_ds_version = self._find_ds_version_by_name('test_version1')
        assert_equal(self.images[1], patched_ds_version.image)
        assert_equal(['pkg1'], patched_ds_version.packages)

    @test(depends_on=[test_mgmt_ds_version_patch])
    def test_mgmt_ds_version_delete(self):
        """Tests the mgmt datastore version delete method."""
        self.client.mgmt_datastore_versions.delete(self.created_version.id)
        assert_equal(202, self.client.last_http_code)

        # Lets match the total count of ds_version,
        # it should get back to original
        ds_versions = self.client.mgmt_datastore_versions.list()
        assert_equal(len(self.ds_versions), len(ds_versions))
