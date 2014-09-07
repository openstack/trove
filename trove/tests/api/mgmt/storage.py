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


from nose.plugins.skip import SkipTest

from proboscis import before_class
from proboscis import test
from proboscis import asserts

from trove import tests
from trove.tests.api.instances import CheckInstance
from trove.tests.api.instances import instance_info
from trove.tests.util import test_config
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements

FAKE_MODE = test_config.values['fake_mode']
GROUP = "dbaas.api.mgmt.storage"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class StorageBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_storage_on_host(self):
        if not FAKE_MODE:
            raise SkipTest("Volume driver currently not working.")
        storage = self.client.storage.index()
        print("storage : %r" % storage)
        for device in storage:
            asserts.assert_true(hasattr(device, 'name'),
                                "device.name: %r" % device.name)
            asserts.assert_true(hasattr(device, 'type'),
                                "device.type: %r" % device.name)
            asserts.assert_true(hasattr(device, 'used'),
                                "device.used: %r" % device.used)

            asserts.assert_true(hasattr(device, 'provision'),
                                "device.provision: %r" % device.provision)
            provision = device.provision
            asserts.assert_true('available' in provision,
                                "provision.available: "
                                + "%r" % provision['available'])
            asserts.assert_true('percent' in provision,
                                "provision.percent: %r" % provision['percent'])
            asserts.assert_true('total' in provision,
                                "provision.total: %r" % provision['total'])

            asserts.assert_true(hasattr(device, 'capacity'),
                                "device.capacity: %r" % device.capacity)
            capacity = device.capacity
            asserts.assert_true('available' in capacity,
                                "capacity.available: "
                                + "%r" % capacity['available'])
            asserts.assert_true('total' in capacity,
                                "capacity.total: %r" % capacity['total'])
        instance_info.storage = storage


@test(groups=[tests.INSTANCES, GROUP],
      depends_on_groups=["dbaas.listing"])
class StorageAfterInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_storage_on_host(self):
        if not FAKE_MODE:
            raise SkipTest("Volume driver currently not working.")
        storage = self.client.storage.index()
        print("storage : %r" % storage)
        print("instance_info.storage : %r" % instance_info.storage)
        allowed_attrs = ['name', 'type', 'used', 'provision', 'capacity']
        for index, device in enumerate(storage):
            CheckInstance(None).contains_allowed_attrs(
                device._info,
                allowed_attrs, msg="Storage")
            asserts.assert_equal(device.name,
                                 instance_info.storage[index].name)
            asserts.assert_equal(device.used,
                                 instance_info.storage[index].used)
            asserts.assert_equal(device.type,
                                 instance_info.storage[index].type)

            provision = instance_info.storage[index].provision
            asserts.assert_equal(device.provision['available'],
                                 provision['available'])
            asserts.assert_equal(device.provision['percent'],
                                 provision['percent'])
            asserts.assert_equal(device.provision['total'], provision['total'])

            capacity = instance_info.storage[index].capacity
            asserts.assert_equal(device.capacity['available'],
                                 capacity['available'])
            asserts.assert_equal(device.capacity['total'], capacity['total'])
