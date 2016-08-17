# Copyright 2016 Tesora Inc.
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

from couchbase.bucket import Bucket
from couchbase import exceptions as cb_except

from trove.tests.scenario.helpers.test_helper import TestHelper
from trove.tests.scenario.runners.test_runners import TestRunner
from trove.tests.util import utils


class CouchbaseHelper(TestHelper):

    def __init__(self, expected_override_name, report):
        super(CouchbaseHelper, self).__init__(expected_override_name, report)

        self._data_cache = dict()

    def get_helper_credentials(self):
        return {'name': 'lite', 'password': 'litepass'}

    def create_client(self, host, *args, **kwargs):
        user = self.get_helper_credentials()
        return self._create_test_bucket(host, user['name'], user['password'])

    def _create_test_bucket(self, host, bucket_name, password):
        return Bucket('couchbase://%s/%s' % (host, bucket_name),
                      password=password)

    # Add data overrides
    def add_actual_data(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        if not self._key_exists(client, data_label, *args, **kwargs):
            self._set_data_point(client, data_label,
                                 self._get_dataset(data_start, data_size))

    @utils.retry((cb_except.TemporaryFailError, cb_except.BusyError))
    def _key_exists(self, client, key, *args, **kwargs):
        return client.get(key, quiet=True).success

    @utils.retry((cb_except.TemporaryFailError, cb_except.BusyError))
    def _set_data_point(self, client, key, value, *args, **kwargs):
        client.insert(key, value)

    def _get_dataset(self, data_start, data_size):
        cache_key = str(data_size)
        if cache_key in self._data_cache:
            return self._data_cache.get(cache_key)

        data = range(data_start, data_start + data_size)
        self._data_cache[cache_key] = data
        return data

    # Remove data overrides
    def remove_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        if self._key_exists(client, data_label, *args, **kwargs):
            self._remove_data_point(client, data_label, *args, **kwargs)

    @utils.retry((cb_except.TemporaryFailError, cb_except.BusyError))
    def _remove_data_point(self, client, key, *args, **kwargs):
        client.remove(key)

    # Verify data overrides
    def verify_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        expected_value = self._get_dataset(data_start, data_size)
        self._verify_data_point(client, data_label, expected_value)

    def _verify_data_point(self, client, key, expected_value, *args, **kwargs):
        value = self._get_data_point(client, key, *args, **kwargs)
        TestRunner.assert_equal(expected_value, value,
                                "Unexpected value '%s' returned from "
                                "Couchbase key '%s'" % (value, key))

    @utils.retry((cb_except.TemporaryFailError, cb_except.BusyError))
    def _get_data_point(self, client, key, *args, **kwargs):
        return client.get(key).value

    def ping(self, host, *args, **kwargs):
        try:
            self.create_client(host, *args, **kwargs)
            return True
        except Exception:
            return False
