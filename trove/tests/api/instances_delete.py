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
import os
import time

from proboscis import asserts
from proboscis.decorators import time_out
from proboscis import SkipTest
from proboscis import test
from troveclient.compat import exceptions

from trove import tests
from trove.tests.api.instances import instance_info
from trove.tests.config import CONFIG
from trove.tests.api import configurations


def do_not_delete_instance():
    return os.environ.get("TESTS_DO_NOT_DELETE_INSTANCE", None) is not None


@test(depends_on_groups=[tests.DBAAS_API_REPLICATION],
      groups=[tests.DBAAS_API_INSTANCES_DELETE],
      enabled=not do_not_delete_instance())
class TestDeleteInstance(object):
    @time_out(3 * 60)
    @test
    def test_delete(self):
        """Delete instance for clean up."""
        if not hasattr(instance_info, "initial_result"):
            raise SkipTest("Instance was never created, skipping test...")
        # Update the report so the logs inside the instance will be saved.
        CONFIG.get_report().update()

        dbaas = instance_info.dbaas
        dbaas.instances.delete(instance_info.id)

        attempts = 0
        try:
            time.sleep(1)
            result = True
            while result is not None:
                attempts += 1
                result = dbaas.instances.get(instance_info.id)
                asserts.assert_equal(200, dbaas.last_http_code)
                asserts.assert_equal("SHUTDOWN", result.status)
                time.sleep(1)
        except exceptions.NotFound:
            pass
        except Exception as ex:
            asserts.fail("A failure occurred when trying to GET instance %s "
                         "for the %d time: %s" %
                         (str(instance_info.id), attempts, str(ex)))

    @test(depends_on=[test_delete])
    def test_instance_status_deleted_in_db(self):
        """test_instance_status_deleted_in_db"""
        dbaas_admin = instance_info.dbaas_admin
        mgmt_details = dbaas_admin.management.index(deleted=True)
        for instance in mgmt_details:
            if instance.id == instance_info.id:
                asserts.assert_equal(instance.service_status, 'DELETED')
                break
        else:
            asserts.fail("Could not find instance %s" % instance_info.id)

    @test(depends_on=[test_instance_status_deleted_in_db])
    def test_delete_datastore(self):
        dbaas_admin = instance_info.dbaas_admin

        datastore = dbaas_admin.datastores.get(
            CONFIG.dbaas_datastore_name_no_versions)
        versions = dbaas_admin.datastore_versions.list(datastore.id)
        for version in versions:
            dbaas_admin.mgmt_datastore_versions.delete(version.id)

        # Delete the datastore
        dbaas_admin.datastores.delete(datastore.id)

    @test(depends_on=[test_instance_status_deleted_in_db])
    def test_delete_configuration(self):
        """Delete configurations created during testing."""
        dbaas_admin = instance_info.dbaas_admin
        configs = dbaas_admin.configurations.list()
        for config in configs:
            if config.name == configurations.CONFIG_NAME:
                dbaas_admin.configurations.delete(config.id)
