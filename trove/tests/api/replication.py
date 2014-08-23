# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.decorators import time_out
from trove.common.utils import generate_uuid
from trove.common.utils import poll_until
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import TIMEOUT_INSTANCE_CREATE
from trove.tests.api.instances import TIMEOUT_INSTANCE_DELETE
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util.server_connection import create_server_connection
from troveclient.compat import exceptions


class SlaveInstanceTestInfo(object):
    """Stores slave instance information."""
    def __init__(self):
        self.id = None
        self.replicated_db = generate_uuid()


GROUP = "dbaas.api.replication"
slave_instance = SlaveInstanceTestInfo()


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP])
class CreateReplicationSlave(object):

    @test
    def test_create_slave(self):
        result = instance_info.dbaas.instances.create(
            instance_info.name + "_slave",
            instance_info.dbaas_flavor_href,
            instance_info.volume,
            slave_of=instance_info.id)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal("BUILD", result.status)
        slave_instance.id = result.id


@test(groups=[GROUP])
class WaitForCreateSlaveToFinish(object):
    """Wait until the instance is created and set up as slave."""

    @test(depends_on=[CreateReplicationSlave.test_create_slave])
    @time_out(TIMEOUT_INSTANCE_CREATE)
    def test_slave_created(self):
        def result_is_active():
            instance = instance_info.dbaas.instances.get(slave_instance.id)
            if instance.status == "ACTIVE":
                return True
            else:
                # If its not ACTIVE, anything but BUILD must be
                # an error.
                assert_equal("BUILD", instance.status)
                if instance_info.volume is not None:
                    assert_equal(instance.volume.get('used', None), None)
                return False
        poll_until(result_is_active)


@test(enabled=(not CONFIG.fake_mode),
      depends_on=[WaitForCreateSlaveToFinish],
      groups=[GROUP])
class VerifySlave(object):

    @test
    @time_out(5 * 60)
    def test_correctly_started_replication(self):

        def slave_is_running():
            server = create_server_connection(slave_instance.id)
            cmd = ("mysqladmin extended-status "
                   "| awk '/Slave_running/{print $4}'")
            stdout, stderr = server.execute(cmd)
            return stdout == "ON\n"

        poll_until(slave_is_running)

    @test(depends_on=[test_correctly_started_replication])
    def test_create_db_on_master(self):
        databases = [{'name': slave_instance.replicated_db}]
        instance_info.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, instance_info.dbaas.last_http_code)

    @test(depends_on=[test_create_db_on_master])
    @time_out(5 * 60)
    def test_database_replicated_on_slave(self):

        def db_is_found():
            databases = instance_info.dbaas.databases.list(slave_instance.id)
            return (slave_instance.replicated_db
                    in [d.name for d in databases])

        poll_until(db_is_found)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSlaveToFinish],
      runs_after=[VerifySlave])
class DeleteSlaveInstance(object):

    @test
    @time_out(TIMEOUT_INSTANCE_DELETE)
    def test_delete_slave_instance(self):
        instance_info.dbaas.instances.delete(slave_instance.id)
        assert_equal(202, instance_info.dbaas.last_http_code)

        def instance_is_gone():
            try:
                instance_info.dbaas.instances.get(slave_instance.id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(instance_is_gone)
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.get,
                      slave_instance.id)
