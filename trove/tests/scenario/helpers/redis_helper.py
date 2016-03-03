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

        self._ds_client_cache = dict()

    def get_client(self, host, *args, **kwargs):
        # We need to cache the Redis client in order to prevent Error 99
        # (Cannot assign requested address) when working with large data sets.
        # A new client may be created frequently due to how the redirection
        # works (see '_execute_with_redirection').
        # The old (now closed) connections however have to wait for about 60s
        # (TIME_WAIT) before the port can be released.
        # This is a feature of the operating system that helps it dealing with
        # packets that arrive after the connection is closed.
        if host in self._ds_client_cache:
            return self._ds_client_cache[host]

        client = self.create_client(host, *args, **kwargs)
        self._ds_client_cache[host] = client
        return client

    def create_client(self, host, *args, **kwargs):
        user = self.get_helper_credentials()
        client = redis.StrictRedis(password=user['password'], host=host)
        return client

    # Add data overrides
    def add_actual_data(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
        test_set = self._get_data_point(host, data_label, *args, **kwargs)
        if not test_set:
            for num in range(data_start, data_start + data_size):
                self._set_data_point(
                    host,
                    self.key_pattern % str(num), self.value_pattern % str(num),
                    *args, **kwargs)
            # now that the data is there, add the label
            self._set_data_point(
                host,
                data_label, self.label_value,
                *args, **kwargs)

    def _set_data_point(self, host, key, value, *args, **kwargs):
        def set_point(client, key, value):
            return client.set(key, value)

        self._execute_with_redirection(
            host, set_point, [key, value], *args, **kwargs)

    def _get_data_point(self, host, key, *args, **kwargs):
        def get_point(client, key):
            return client.get(key)

        return self._execute_with_redirection(
            host, get_point, [key], *args, **kwargs)

    def _execute_with_redirection(self, host, callback, callback_args,
                                  *args, **kwargs):
        """Redis clustering is a relatively new feature still not supported
        in a fully transparent way by all clients.
        The application itself is responsible for connecting to the right node
        when accessing a key in a Redis cluster instead.

        Clients may be redirected to other nodes by redirection errors:

            redis.exceptions.ResponseError: MOVED 10778 10.64.0.2:6379

        This method tries to execute a given callback on a given host.
        If it gets a redirection error it parses the new host from the response
        and issues the same callback on this new host.
        """
        client = self.get_client(host, *args, **kwargs)
        try:
            return callback(client, *callback_args)
        except redis.exceptions.ResponseError as ex:
            response = str(ex)
            if response:
                tokens = response.split()
                if tokens[0] == 'MOVED':
                    redirected_host = tokens[2].split(':')[0]
                    if redirected_host:
                        return self._execute_with_redirection(
                            redirected_host, callback, callback_args,
                            *args, **kwargs)
            raise ex

    # Remove data overrides
    def remove_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        test_set = self._get_data_point(host, data_label, *args, **kwargs)
        if test_set:
            for num in range(data_start, data_start + data_size):
                self._expire_data_point(host, self.key_pattern % str(num),
                                        *args, **kwargs)
            # now that the data is gone, remove the label
            self._expire_data_point(host, data_label, *args, **kwargs)

    def _expire_data_point(self, host, key, *args, **kwargs):
        def expire_point(client, key):
            return client.expire(key, 0)

        self._execute_with_redirection(
            host, expire_point, [key], *args, **kwargs)

    # Verify data overrides
    def verify_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        # make sure the data is there - tests edge cases and a random one
        self._verify_data_point(host, data_label, self.label_value,
                                *args, **kwargs)
        midway_num = data_start + int(data_size / 2)
        random_num = random.randint(data_start + 2,
                                    data_start + data_size - 3)
        for num in [data_start,
                    data_start + 1,
                    midway_num,
                    random_num,
                    data_start + data_size - 2,
                    data_start + data_size - 1]:
            self._verify_data_point(host,
                                    self.key_pattern % num,
                                    self.value_pattern % num,
                                    *args, **kwargs)
        # negative tests
        for num in [data_start - 1,
                    data_start + data_size]:
            self._verify_data_point(host, self.key_pattern % num, None,
                                    *args, **kwargs)

    def _verify_data_point(self, host, key, expected_value, *args, **kwargs):
        value = self._get_data_point(host, key, *args, **kwargs)
        TestRunner.assert_equal(expected_value, value,
                                "Unexpected value '%s' returned from Redis "
                                "key '%s'" % (value, key))

    def get_dynamic_group(self):
        return {'hz': 15}

    def get_non_dynamic_group(self):
        return {'databases': 24}

    def get_invalid_groups(self):
        return [{'hz': 600}, {'databases': -1}, {'databases': 'string_value'}]
