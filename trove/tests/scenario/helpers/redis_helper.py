# Copyright 2015 Tesora Inc.
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

import random
import redis

from trove.tests.scenario.helpers.test_helper import TestHelper
from trove.tests.scenario.runners.test_runners import TestRunner


class RedisHelper(TestHelper):

    def __init__(self, expected_override_name):
        super(RedisHelper, self).__init__(expected_override_name)

        self.key_pattern = 'user:%s'
        self.value_pattern = 'id:%s'
        self.label_value = 'value_set'

    def create_client(self, host, *args, **kwargs):
        user = self.get_helper_credentials()
        client = redis.StrictRedis(password=user['password'], host=host)
        return client

    # Add data overrides
    def add_actual_data(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        test_set = client.get(data_label)
        if not test_set:
            for num in range(data_start, data_start + data_size):
                client.set(self.key_pattern % str(num),
                           self.value_pattern % str(num))
            # now that the data is there, add the label
            client.set(data_label, self.label_value)

    # Remove data overrides
    def remove_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        test_set = client.get(data_label)
        if test_set:
            for num in range(data_start, data_start + data_size):
                client.expire(self.key_pattern % str(num), 0)
            # now that the data is gone, remove the label
            client.expire(data_label, 0)

    # Verify data overrides
    def verify_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        # make sure the data is there - tests edge cases and a random one
        self._verify_data_point(client, data_label, self.label_value)
        midway_num = data_start + int(data_size / 2)
        random_num = random.randint(data_start + 2,
                                    data_start + data_size - 3)
        for num in [data_start,
                    data_start + 1,
                    midway_num,
                    random_num,
                    data_start + data_size - 2,
                    data_start + data_size - 1]:
            self._verify_data_point(client,
                                    self.key_pattern % num,
                                    self.value_pattern % num)
        # negative tests
        for num in [data_start - 1,
                    data_start + data_size]:
            self._verify_data_point(client, self.key_pattern % num, None)

    def _verify_data_point(self, client, key, expected_value):
        value = client.get(key)
        TestRunner.assert_equal(expected_value, value,
                                "Unexpected value '%s' returned from Redis "
                                "key '%s'" % (value, key))

    def get_dynamic_group(self):
        return {'hz': 15}

    def get_non_dynamic_group(self):
        return {'databases': 24}

    def get_invalid_groups(self):
        return [{'hz': 600}, {'databases': -1}, {'databases': 'string_value'}]
