
from proboscis.asserts import assert_equal
from proboscis import test
from proboscis import before_class

from trove.common.utils import poll_until
from trove.tests.util import create_client


class InstanceGenerator(object):

    def __init__(self, client, status=None, name=None, flavor=None,
                 account_id=None, created_at=None, databases=None, users=None,
                 volume_size=None):
        self.client = client
        self.status = status
        self.name = name
        self.flavor = flavor
        self.account_id = account_id
        self.databases = databases
        self.users = users
        self.volume_size = volume_size
        self.id = None

    def create_instance(self):
        #make the call to create the instance
        instance = self.client.instances.create(self.name, self.flavor,
                                self.volume_size, self.databases, self.users)
        self.client.assert_http_code(200)

        #verify we are in a build state
        assert_equal(instance.status, "BUILD")
        #pull out the ID
        self.id = instance.id

        return instance

    def wait_for_build_to_finish(self):
        poll_until(lambda: self.client.instance.get(self.id),
                   lambda instance: instance.status != "BUILD",
                   time_out=600)

    def get_active_instance(self):
        instance = self.client.instance.get(self.id)
        self.client.assert_http_code(200)

        #check the container name
        assert_equal(instance.name, self.name)

        #pull out volume info and verify
        assert_equal(str(instance.volume_size), str(self.volume_size))

        #pull out the flavor and verify
        assert_equal(str(instance.flavor), str(self.flavor))

        return instance


@test(groups=['smoke', 'positive'])
class CreateInstance(object):

    @before_class
    def set_up(self):
        client = create_client(is_admin=False)
        name = 'test_createInstance_container'
        flavor = 1
        volume_size = 1
        db_name = 'test_db'
        databases = [
            {
                "name": db_name
            }
        ]
        users = [
            {
                "name": "lite",
                "password": "litepass",
                "databases": [{"name": db_name}]
            }
        ]

        #create the Instance
        instance = InstanceGenerator(client, name=self.name,
                                     flavor=flavor,
                                     volume_size=self.volume_size,
                                     databases=databases, users=users)
        instance.create_instance()

        #wait for the instance
        instance.wait_for_build_to_finish()

        #get the active instance
        inst = instance.get_active_instance()

        #list out the databases for our instance and verify the db name
        dbs = client.databases.list(inst.id)
        client.assert_http_code(200)

        assert_equal(len(dbs), 1)
        assert_equal(dbs[0].name, instance.db_name)

        client.instance.delete(inst.id)
        client.assert_http_code(202)
