import time

from proboscis import before_class
from proboscis import test
from proboscis.asserts import *
from proboscis.decorators import time_out

from troveclient import exceptions
from trove.tests.util import create_dbaas_client
from trove.tests.util import poll_until
from trove.tests.util import test_config
from trove.tests.util.users import Requirements
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import VOLUME_SUPPORT


class TestBase(object):

    def set_up(self):
        reqs = Requirements(is_admin=True)
        self.user = test_config.users.find_user(reqs)
        self.dbaas = create_dbaas_client(self.user)

    def create_instance(self, name, size=1):
        volume = None
        if VOLUME_SUPPORT:
            volume = {'size': size}
        result = self.dbaas.instances.create(name,
                                             instance_info.dbaas_flavor_href,
                                             volume, [], [])
        return result.id

    def wait_for_instance_status(self, instance_id, status="ACTIVE"):
        poll_until(lambda: self.dbaas.instances.get(instance_id),
                   lambda instance: instance.status == status,
                   time_out=10)

    def wait_for_instance_task_status(self, instance_id, description):
        poll_until(lambda: self.dbaas.management.show(instance_id),
                   lambda instance: instance.task_description == description,
                   time_out=10)

    def is_instance_deleted(self, instance_id):
        while True:
            try:
                instance = self.dbaas.instances.get(instance_id)
            except exceptions.NotFound:
                return True
            time.sleep(.5)

    def get_task_info(self, instance_id):
        instance = self.dbaas.management.show(instance_id)
        return instance.status, instance.task_description

    def delete_instance(self, instance_id, assert_deleted=True):
        instance = self.dbaas.instances.get(instance_id)
        instance.delete()
        if assert_deleted:
            assert_true(self.is_instance_deleted(instance_id))

    def delete_errored_instance(self, instance_id):
        self.wait_for_instance_status(instance_id, 'ERROR')
        status, desc = self.get_task_info(instance_id)
        assert_equal(status, "ERROR")
        self.delete_instance(instance_id)


@test(runs_after_groups=["services.initialize"],
      groups=['dbaas.api.instances.delete'])
class ErroredInstanceDelete(TestBase):
    """
    Test that an instance in an ERROR state is actually deleted when delete
    is called.
    """

    @before_class
    def set_up(self):
        """Create some flawed instances."""
        super(ErroredInstanceDelete, self).set_up()
        # Create an instance that fails during server prov.
        self.server_error = self.create_instance('test_SERVER_ERROR')
        if VOLUME_SUPPORT:
            # Create an instance that fails during volume prov.
            self.volume_error = self.create_instance('test_VOLUME_ERROR',
                                                     size=9)
        else:
            self.volume_error = None
        # Create an instance that fails during DNS prov.
        #self.dns_error = self.create_instance('test_DNS_ERROR')
        # Create an instance that fails while it's been deleted the first time.
        self.delete_error = self.create_instance('test_ERROR_ON_DELETE')

    @test
    @time_out(30)
    def delete_server_error(self):
        self.delete_errored_instance(self.server_error)

    @test(enabled=VOLUME_SUPPORT)
    @time_out(30)
    def delete_volume_error(self):
        self.delete_errored_instance(self.volume_error)

    @test(enabled=False)
    @time_out(30)
    def delete_dns_error(self):
        self.delete_errored_instance(self.dns_error)

    @test
    @time_out(30)
    def delete_error_on_delete_instance(self):
        id = self.delete_error
        self.wait_for_instance_status(id, 'ACTIVE')
        self.wait_for_instance_task_status(id, 'No tasks for the instance.')
        instance = self.dbaas.management.show(id)
        assert_equal(instance.status, "ACTIVE")
        assert_equal(instance.task_description, 'No tasks for the instance.')
        # Try to delete the instance. This fails the first time due to how
        # the test fake  is setup.
        self.delete_instance(id, assert_deleted=False)
        instance = self.dbaas.management.show(id)
        assert_equal(instance.status, "SHUTDOWN")
        assert_equal(instance.task_description, "Deleting the instance.")
        # Try a second time. This will succeed.
        self.delete_instance(id)
