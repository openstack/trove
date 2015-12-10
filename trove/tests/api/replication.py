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
from time import sleep

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.decorators import time_out
from proboscis import SkipTest
from proboscis import test
from troveclient.compat import exceptions

from trove.common.utils import generate_uuid
from trove.common.utils import poll_until
from trove.tests.api.instances import CheckInstance
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import TIMEOUT_INSTANCE_CREATE
from trove.tests.api.instances import TIMEOUT_INSTANCE_DELETE
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util.server_connection import create_server_connection


class SlaveInstanceTestInfo(object):
    """Stores slave instance information."""
    def __init__(self):
        self.id = None
        self.replicated_db = generate_uuid()


GROUP = "dbaas.api.replication"
slave_instance = SlaveInstanceTestInfo()
existing_db_on_master = generate_uuid()


def _get_user_count(server_info):
    cmd = ('mysql -BNq -e \\\'select count\\(*\\) from mysql.user'
           ' where user like \\\"slave_%\\\"\\\'')
    server = create_server_connection(server_info.id)
    stdout, stderr = server.execute(cmd)
    return int(stdout.rstrip())


def slave_is_running(running=True):

    def check_slave_is_running():
        server = create_server_connection(slave_instance.id)
        cmd = ("mysqladmin extended-status "
               "| awk '/Slave_running/{print $4}'")
        stdout, stderr = server.execute(cmd)
        expected = "ON" if running else "OFF"
        return stdout.rstrip() == expected

    return check_slave_is_running


def instance_is_active(id):
    instance = instance_info.dbaas.instances.get(id)
    if instance.status == "ACTIVE":
        return True
    else:
        assert_true(instance.status in ['PROMOTE', 'EJECT', 'BUILD', 'BACKUP'])
        return False


def create_slave():
    result = instance_info.dbaas.instances.create(
        instance_info.name + "_slave",
        instance_info.dbaas_flavor_href,
        instance_info.volume,
        datastore=instance_info.dbaas_datastore,
        datastore_version=instance_info.dbaas_datastore_version,
        slave_of=instance_info.id)
    assert_equal(200, instance_info.dbaas.last_http_code)
    assert_equal("BUILD", result.status)
    return result.id


def validate_slave(master, slave):
    new_slave = instance_info.dbaas.instances.get(slave.id)
    assert_equal(200, instance_info.dbaas.last_http_code)
    ns_dict = new_slave._info
    CheckInstance(ns_dict).slave_of()
    assert_equal(master.id, ns_dict['replica_of']['id'])


def validate_master(master, slaves):
    new_master = instance_info.dbaas.instances.get(master.id)
    assert_equal(200, instance_info.dbaas.last_http_code)
    nm_dict = new_master._info
    CheckInstance(nm_dict).slaves()
    master_ids = set([replica['id'] for replica in nm_dict['replicas']])
    asserted_ids = set([slave.id for slave in slaves])
    assert_true(asserted_ids.issubset(master_ids))


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP])
class CreateReplicationSlave(object):

    @test
    def test_replica_provisioning_with_missing_replica_source(self):
        assert_raises(exceptions.NotFound,
                      instance_info.dbaas.instances.create,
                      instance_info.name + "_slave",
                      instance_info.dbaas_flavor_href,
                      instance_info.volume,
                      slave_of="Missing replica source")
        assert_equal(404, instance_info.dbaas.last_http_code)

    @test
    def test_create_db_on_master(self):
        databases = [{'name': existing_db_on_master}]
        # Ensure that the auth_token in the dbaas client is not stale
        instance_info.dbaas.authenticate()
        instance_info.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, instance_info.dbaas.last_http_code)

    @test(runs_after=['test_create_db_on_master'])
    def test_create_slave(self):
        slave_instance.id = create_slave()


@test(groups=[GROUP])
class WaitForCreateSlaveToFinish(object):
    """Wait until the instance is created and set up as slave."""

    @test(depends_on=[CreateReplicationSlave.test_create_slave])
    @time_out(TIMEOUT_INSTANCE_CREATE)
    def test_slave_created(self):
        poll_until(lambda: instance_is_active(slave_instance.id))


@test(enabled=(not CONFIG.fake_mode),
      depends_on=[WaitForCreateSlaveToFinish],
      groups=[GROUP])
class VerifySlave(object):

    def db_is_found(self, database_to_find):

        def find_database():
            databases = instance_info.dbaas.databases.list(slave_instance.id)
            return (database_to_find
                    in [d.name for d in databases])

        return find_database

    @test
    @time_out(5 * 60)
    def test_correctly_started_replication(self):
        poll_until(slave_is_running())

    @test(runs_after=[test_correctly_started_replication])
    def test_backup_deleted(self):
        backup = instance_info.dbaas.instances.backups(instance_info.id)
        assert_equal(len(backup), 0)

    @test(depends_on=[test_correctly_started_replication])
    def test_slave_is_read_only(self):
        cmd = "mysql -BNq -e \\\'select @@read_only\\\'"
        server = create_server_connection(slave_instance.id)
        stdout, stderr = server.execute(cmd)
        assert_equal(stdout, "1\n")

    @test(depends_on=[test_slave_is_read_only])
    def test_create_db_on_master(self):
        databases = [{'name': slave_instance.replicated_db}]
        instance_info.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, instance_info.dbaas.last_http_code)

    @test(depends_on=[test_create_db_on_master])
    @time_out(5 * 60)
    def test_database_replicated_on_slave(self):
        poll_until(self.db_is_found(slave_instance.replicated_db))

    @test(runs_after=[test_database_replicated_on_slave])
    @time_out(5 * 60)
    def test_existing_db_exists_on_slave(self):
        poll_until(self.db_is_found(existing_db_on_master))

    @test(depends_on=[test_existing_db_exists_on_slave])
    def test_slave_user_exists(self):
        assert_equal(_get_user_count(slave_instance), 1)
        assert_equal(_get_user_count(instance_info), 1)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSlaveToFinish],
      runs_after=[VerifySlave])
class TestInstanceListing(object):
    """Test replication information in instance listing."""

    @test
    def test_get_slave_instance(self):
        validate_slave(instance_info, slave_instance)

    @test
    def test_get_master_instance(self):
        validate_master(instance_info, [slave_instance])


@test(groups=[GROUP],
      depends_on=[WaitForCreateSlaveToFinish],
      runs_after=[TestInstanceListing])
class TestReplicationFailover(object):
    """Test replication failover functionality."""

    @staticmethod
    def promote(master, slave):
        if CONFIG.fake_mode:
            raise SkipTest("promote_replica_source not supported in fake mode")

        instance_info.dbaas.instances.promote_to_replica_source(slave)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: instance_is_active(slave.id))
        validate_master(slave, [master])
        validate_slave(slave, master)

    @test
    def test_promote_master(self):
        if CONFIG.fake_mode:
            raise SkipTest("promote_master not supported in fake mode")

        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.promote_to_replica_source,
                      instance_info.id)

    @test
    def test_eject_slave(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.eject_replica_source,
                      slave_instance.id)

    @test
    def test_eject_valid_master(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.eject_replica_source,
                      instance_info.id)

    @test(depends_on=[test_promote_master, test_eject_slave,
                      test_eject_valid_master])
    def test_promote_to_replica_source(self):
        TestReplicationFailover.promote(instance_info, slave_instance)

    @test(depends_on=[test_promote_to_replica_source])
    def test_promote_back_to_replica_source(self):
        TestReplicationFailover.promote(slave_instance, instance_info)

    @test(depends_on=[test_promote_back_to_replica_source], enabled=False)
    def add_second_slave(self):
        if CONFIG.fake_mode:
            raise SkipTest("three site promote not supported in fake mode")

        self._third_slave = SlaveInstanceTestInfo()
        self._third_slave.id = create_slave()
        poll_until(lambda: instance_is_active(self._third_slave.id))
        poll_until(slave_is_running())
        sleep(30)
        validate_master(instance_info, [slave_instance, self._third_slave])
        validate_slave(instance_info, self._third_slave)

    @test(depends_on=[add_second_slave], enabled=False)
    def test_three_site_promote(self):
        if CONFIG.fake_mode:
            raise SkipTest("three site promote not supported in fake mode")

        TestReplicationFailover.promote(instance_info, self._third_slave)
        validate_master(self._third_slave, [slave_instance, instance_info])
        validate_slave(self._third_slave, instance_info)

    @test(depends_on=[test_three_site_promote], enabled=False)
    def disable_master(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        cmd = "sudo service trove-guestagent stop"
        server = create_server_connection(self._third_slave.id)
        stdout, stderr = server.execute(cmd)
        assert_equal(stdout, "1\n")

    @test(depends_on=[disable_master], enabled=False)
    def test_eject_replica_master(self):
        if CONFIG.fake_mode:
            raise SkipTest("eject_replica_source not supported in fake mode")

        sleep(90)
        instance_info.dbaas.instances.eject_replica_source(self._third_slave)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: instance_is_active(self._third_slave.id))
        validate_master(instance_info, [slave_instance])
        validate_slave(instance_info, slave_instance)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSlaveToFinish],
      runs_after=[TestReplicationFailover])
class DetachReplica(object):

    @test
    def delete_before_detach_replica(self):
        assert_raises(exceptions.Forbidden,
                      instance_info.dbaas.instances.delete,
                      instance_info.id)

    @test
    @time_out(5 * 60)
    def test_detach_replica(self):
        if CONFIG.fake_mode:
            raise SkipTest("Detach replica not supported in fake mode")

        instance_info.dbaas.instances.edit(slave_instance.id,
                                           detach_replica_source=True)
        assert_equal(202, instance_info.dbaas.last_http_code)

        poll_until(slave_is_running(False))

    @test(depends_on=[test_detach_replica])
    @time_out(5 * 60)
    def test_slave_is_not_read_only(self):
        if CONFIG.fake_mode:
            raise SkipTest("Test not_read_only not supported in fake mode")

        # wait until replica is no longer read only
        def check_not_read_only():
            cmd = "mysql -BNq -e \\\'select @@read_only\\\'"
            server = create_server_connection(slave_instance.id)
            stdout, stderr = server.execute(cmd)
            if (stdout.rstrip() != "0"):
                return False
            else:
                return True
        poll_until(check_not_read_only)


@test(groups=[GROUP],
      depends_on=[WaitForCreateSlaveToFinish],
      runs_after=[DetachReplica])
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
