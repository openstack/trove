# Copyright 2016 IBM Corporation
#
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

import couchdb
from trove.tests.scenario.helpers.test_helper import TestHelper
from trove.tests.scenario.runners.test_runners import TestRunner


class CouchdbHelper(TestHelper):

    def __init__(self, expected_override_name):
        super(CouchdbHelper, self).__init__(expected_override_name)
        self._data_cache = dict()
        self.field_name = 'ff-%s'
        self.database = 'foodb'

    def create_client(self, host, *args, **kwargs):
        url = 'http://' + host + ':5984/'
        server = couchdb.Server(url)
        return server

    def add_actual_data(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
        client = self.get_client(host, *args, **kwargs)
        db = client.create(self.database + '_' + data_label)
        doc = {}
        doc_id, doc_rev = db.save(doc)
        data = self._get_dataset(data_size)
        doc = db.get(doc_id)
        for value in data:
            key = self.field_name % value
            doc[key] = value
        db.save(doc)

    def _get_dataset(self, data_size):
        cache_key = str(data_size)
        if cache_key in self._data_cache:
            return self._data_cache.get(cache_key)

        data = self._generate_dataset(data_size)
        self._data_cache[cache_key] = data
        return data

    def _generate_dataset(self, data_size):
        return range(1, data_size + 1)

    def remove_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        client = self.get_client(host)
        db = client[self.database + "_" + data_label]
        client.delete(db)

    def verify_actual_data(self, data_label, data_start, data_size, host,
                           *args, **kwargs):
        expected_data = self._get_dataset(data_size)
        client = self.get_client(host, *args, **kwargs)
        db = client[self.database + '_' + data_label]
        actual_data = []

        TestRunner.assert_equal(len(db), 1)

        for i in db:
            items = db[i].items()
            actual_data = ([value for key, value in items
                           if key not in ['_id', '_rev']])

        TestRunner.assert_equal(len(expected_data),
                                len(actual_data),
                                "Unexpected number of result rows.")

        for expected_row in expected_data:
            TestRunner.assert_true(expected_row in actual_data,
                                   "Row not found in the result set: %s"
                                   % expected_row)
