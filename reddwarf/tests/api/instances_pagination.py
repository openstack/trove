from proboscis.decorators import time_out
from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_is
from proboscis.asserts import assert_is_not
from proboscis.asserts import assert_is_none
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail
import time

from reddwarfclient import exceptions
from reddwarf.tests import util
from reddwarf.tests.util import create_dbaas_client
from reddwarf.tests.util import test_config
from reddwarf.tests.util.users import Requirements


class TestBase(object):

    def set_up(self):
        """Create a ton of instances."""
        reqs = Requirements(is_admin=False)
        self.user = test_config.users.find_user(reqs)
        self.dbaas = create_dbaas_client(self.user)

    def delete_instances(self):
        chunk = 0
        while True:
            chunk += 1
            attempts = 0
            instances = self.dbaas.instances.list()
            if len(instances) == 0:
                break
            # Sit around and try to delete this chunk.
            while True:
                instance_results = []
                attempts += 1
                deleted_count = 0
                for instance in instances:
                    try:
                        instance.delete()
                        result = "[w]"
                    except exceptions.UnprocessableEntity:
                        result = "[W]"
                    except exceptions.NotFound:
                        result = "[O]"
                        deleted_count += 1
                    except Exception:
                        result = "[X]"
                    instance_results.append(result)
                print("Chunk %d, attempt %d : %s"
                      % (chunk, attempts, ",".join(instance_results)))
                if deleted_count == len(instances):
                    break
                time.sleep(0.2)

    def create_instances(self):
        self.ids = []
        for index in range(self.max):
            name = "multi-%03d" % index
            result = self.dbaas.instances.create(name, 1,
                                                 {'size': 1}, [], [])
            self.ids.append(result.id)
        # Sort the list of IDs in order, so we can confirm the lists pagination
        # returns is also sorted correctly.
        self.ids.sort()

    @staticmethod
    def assert_instances_sorted_by_ids(instances):
        # Assert that the strings are always increasing.
        last_id = ""
        for instance in instances:
            assert_true(last_id < instance.id)

    def print_list(self, instances):
        print("Length = %d" % len(instances))
        print(",".join([instance.id for instance in instances]))

    def test_pagination(self, requested_limit, requested_marker,
                        expected_length, expected_marker, expected_last_item):
        instances = self.dbaas.instances.list(limit=requested_limit,
                                              marker=requested_marker)
        marker = instances.next

        self.print_list(instances)

        # Better get as many as we asked for.
        assert_equal(len(instances), expected_length)
        # The last one should be roughly this one in the list.
        assert_equal(instances[-1].id, expected_last_item)
        # Because limit < count, the marker must be something.
        if expected_marker:
            assert_is_not(marker, None)
            assert_equal(marker, expected_marker)
        else:
            assert_is_none(marker)
        self.assert_instances_sorted_by_ids(instances)


@test(runs_after_groups=["dbaas.guest.shutdown"],
      groups=['dbaas.api.instances.pagination'])
class SimpleCreateAndDestroy(TestBase):
    """
    It turns out a big part of guaranteeing pagination works is to make sure
    we can create a big batch of instances and delete them without problems.
    Even in fake mode though its worth it to check this is the case.
    """

    max = 5

    @before_class
    def set_up(self):
        """Create a ton of instances."""
        super(SimpleCreateAndDestroy, self).set_up()
        self.delete_instances()

    @test
    def spin_up(self):
        self.create_instances()

    @after_class(always_run=True)
    def tear_down(self):
        self.delete_instances()


@test(runs_after_groups=["dbaas.guest.shutdown"],
      groups=['dbaas.api.instances.pagination'])
class InstancePagination50(TestBase):

    max = 50

    @before_class
    def set_up(self):
        """Create a ton of instances."""
        super(InstancePagination50, self).set_up()
        self.delete_instances()
        self.create_instances()

    @after_class(always_run=True)
    def tear_down(self):
        """Tear down all instances."""
        self.delete_instances()

    @test
    def pagination_short(self):
        self.test_pagination(requested_limit=10, requested_marker=None,
                             expected_length=10, expected_marker=self.ids[9],
                             expected_last_item=self.ids[9])

    @test
    def pagination_default(self):
        self.test_pagination(requested_limit=None, requested_marker=None,
                             expected_length=20, expected_marker=self.ids[19],
                             expected_last_item=self.ids[19])

    @test
    def pagination_full(self):
        self.test_pagination(requested_limit=50, requested_marker=None,
                             expected_length=20, expected_marker=self.ids[19],
                             expected_last_item=self.ids[19])


@test(runs_after_groups=["dbaas.guest.shutdown"],
      groups=['dbaas.api.instances.pagination'])
class InstancePagination20(TestBase):

    max = 20

    @before_class
    def set_up(self):
        """Create a ton of instances."""
        super(InstancePagination20, self).set_up()
        self.delete_instances()
        self.create_instances()

    @after_class(always_run=True)
    def tear_down(self):
        """Tear down all instances."""
        self.delete_instances()

    @test
    def pagination_short(self):
        self.test_pagination(requested_limit=10, requested_marker=None,
                             expected_length=10, expected_marker=self.ids[9],
                             expected_last_item=self.ids[9])

    @test
    def pagination_default(self):
        self.test_pagination(requested_limit=None, requested_marker=None,
                             expected_length=20, expected_marker=None,
                             expected_last_item=self.ids[19])

    @test
    def pagination_full(self):
        self.test_pagination(requested_limit=20, requested_marker=None,
                             expected_length=20, expected_marker=None,
                             expected_last_item=self.ids[19])

    @test
    def pagination_overkill(self):
        self.test_pagination(requested_limit=30, requested_marker=None,
                             expected_length=20, expected_marker=None,
                             expected_last_item=self.ids[19])

    @test
    def pagination_last_half(self):
        self.test_pagination(requested_limit=10, requested_marker=self.ids[9],
                             expected_length=10, expected_marker=None,
                             expected_last_item=self.ids[19])

    @test
    def pagination_third_quarter(self):
        self.test_pagination(requested_limit=5, requested_marker=self.ids[9],
                             expected_length=5, expected_marker=self.ids[14],
                             expected_last_item=self.ids[14])

    @test
    def pagination_fourth_quarter(self):
        self.test_pagination(requested_limit=20, requested_marker=self.ids[14],
                             expected_length=5, expected_marker=None,
                             expected_last_item=self.ids[19])
