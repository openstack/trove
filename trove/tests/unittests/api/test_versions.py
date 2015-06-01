# Copyright 2013 OpenStack Foundation
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from mock import Mock

from trove.tests.unittests import trove_testtools
from trove.versions import BaseVersion
from trove.versions import Version
from trove.versions import VersionDataView
from trove.versions import VERSIONS
from trove.versions import VersionsAPI
from trove.versions import VersionsController
from trove.versions import VersionsDataView


BASE_URL = 'http://localhost'


class VersionsControllerTest(trove_testtools.TestCase):

    def setUp(self):
        super(VersionsControllerTest, self).setUp()
        self.controller = VersionsController()
        self.assertIsNotNone(self.controller,
                             "VersionsController instance was None")

    def test_index_json(self):
        request = Mock()
        result = self.controller.index(request)
        self.assertIsNotNone(result,
                             'Result was None')
        result._data = Mock()
        result._data.data_for_json = \
            lambda: {'status': 'CURRENT',
                     'updated': '2012-08-01T00:00:00Z',
                     'id': 'v1.0',
                     'links': [{'href': 'http://localhost/v1.0/',
                                'rel': 'self'}]}

        # can be anything but xml
        json_data = result.data("application/json")

        self.assertIsNotNone(json_data,
                             'Result json_data was None')
        self.assertEqual('v1.0', json_data['id'],
                         'Version id is incorrect')
        self.assertEqual('CURRENT', json_data['status'],
                         'Version status is incorrect')
        self.assertEqual('2012-08-01T00:00:00Z', json_data['updated'],
                         'Version updated value is incorrect')

    def test_show_json(self):
        request = Mock()
        request.url_version = '1.0'
        result = self.controller.show(request)
        self.assertIsNotNone(result,
                             'Result was None')
        json_data = result.data("application/json")
        self.assertIsNotNone(json_data, "JSON data was None")

        version = json_data.get('version', None)
        self.assertIsNotNone(version, "Version was None")

        self.assertEqual('CURRENT', version['status'],
                         "Version status was not 'CURRENT'")
        self.assertEqual('2012-08-01T00:00:00Z', version['updated'],
                         "Version updated was not '2012-08-01T00:00:00Z'")
        self.assertEqual('v1.0', version['id'], "Version id was not 'v1.0'")


class BaseVersionTestCase(trove_testtools.TestCase):

    def setUp(self):
        super(BaseVersionTestCase, self).setUp()

        id = VERSIONS['1.0']['id']
        status = VERSIONS['1.0']['status']
        base_url = BASE_URL
        updated = VERSIONS['1.0']['updated']

        self.base_version = BaseVersion(id, status, base_url, updated)
        self.assertIsNotNone(self.base_version,
                             'BaseVersion instance was None')

    def test_data(self):
        data = self.base_version.data()
        self.assertIsNotNone(data, 'Base Version data was None')

        self.assertTrue(type(data) is dict,
                        "Base Version data is not a dict")
        self.assertEqual('CURRENT', data['status'],
                         "Data status was not 'CURRENT'")
        self.assertEqual('2012-08-01T00:00:00Z', data['updated'],
                         "Data updated was not '2012-08-01T00:00:00Z'")
        self.assertEqual('v1.0', data['id'],
                         "Data status was not 'v1.0'")

    def test_url(self):
        url = self.base_version.url()
        self.assertIsNotNone(url, 'Url was None')
        self.assertEqual('http://localhost/v1.0/', url,
                         "Base Version url is incorrect")


class VersionTestCase(trove_testtools.TestCase):

    def setUp(self):
        super(VersionTestCase, self).setUp()

        id = VERSIONS['1.0']['id']
        status = VERSIONS['1.0']['status']
        base_url = BASE_URL
        updated = VERSIONS['1.0']['updated']

        self.version = Version(id, status, base_url, updated)
        self.assertIsNotNone(self.version,
                             'Version instance was None')

    def test_url_no_trailing_slash(self):
        url = self.version.url()
        self.assertIsNotNone(url, 'Version url was None')
        self.assertEqual(BASE_URL + '/', url,
                         'Base url value was incorrect')

    def test_url_with_trailing_slash(self):
        self.version.base_url = 'http://localhost/'
        url = self.version.url()
        self.assertEqual(BASE_URL + '/', url,
                         'Base url value was incorrect')


class VersionDataViewTestCase(trove_testtools.TestCase):

    def setUp(self):
        super(VersionDataViewTestCase, self).setUp()

        # get a version object first
        id = VERSIONS['1.0']['id']
        status = VERSIONS['1.0']['status']
        base_url = BASE_URL
        updated = VERSIONS['1.0']['updated']

        self.version = Version(id, status, base_url, updated)
        self.assertIsNotNone(self.version,
                             'Version instance was None')

        # then create an instance of VersionDataView
        self.version_data_view = VersionDataView(self.version)
        self.assertIsNotNone(self.version_data_view,
                             'Version Data view instance was None')

    def test_data_for_json(self):
        json_data = self.version_data_view.data_for_json()
        self.assertIsNotNone(json_data, "JSON data was None")
        self.assertTrue(type(json_data) is dict,
                        "JSON version data is not a dict")
        self.assertIsNotNone(json_data.get('version'),
                             "Dict json_data has no key 'version'")
        data = json_data['version']
        self.assertIsNotNone(data, "JSON data version was None")
        self.assertEqual('CURRENT', data['status'],
                         "Data status was not 'CURRENT'")
        self.assertEqual('2012-08-01T00:00:00Z', data['updated'],
                         "Data updated was not '2012-08-01T00:00:00Z'")
        self.assertEqual('v1.0', data['id'],
                         "Data status was not 'v1.0'")


class VersionsDataViewTestCase(trove_testtools.TestCase):

    def setUp(self):
        super(VersionsDataViewTestCase, self).setUp()

        # get a version object, put it in a list
        self.versions = []

        id = VERSIONS['1.0']['id']
        status = VERSIONS['1.0']['status']
        base_url = BASE_URL
        updated = VERSIONS['1.0']['updated']

        self.version = Version(id, status, base_url, updated)
        self.assertIsNotNone(self.version,
                             'Version instance was None')
        self.versions.append(self.version)

        # then create an instance of VersionsDataView
        self.versions_data_view = VersionsDataView(self.versions)
        self.assertIsNotNone(self.versions_data_view,
                             'Versions Data view instance was None')

    def test_data_for_json(self):
        json_data = self.versions_data_view.data_for_json()
        self.assertIsNotNone(json_data, "JSON data was None")
        self.assertTrue(type(json_data) is dict,
                        "JSON versions data is not a dict")
        self.assertIsNotNone(json_data.get('versions', None),
                             "Dict json_data has no key 'versions'")
        versions = json_data['versions']
        self.assertIsNotNone(versions, "Versions was None")
        self.assertTrue(len(versions) == 1, "Versions length != 1")

        # explode the version object
        versions_data = [v.data() for v in self.versions]

        d1 = versions_data.pop()
        d2 = versions.pop()
        self.assertEqual(d1['id'], d2['id'],
                         "Version ids are not equal")


class VersionAPITestCase(trove_testtools.TestCase):

    def setUp(self):
        super(VersionAPITestCase, self).setUp()

    def test_instance(self):
        self.versions_api = VersionsAPI()
        self.assertIsNotNone(self.versions_api,
                             "VersionsAPI instance was None")
