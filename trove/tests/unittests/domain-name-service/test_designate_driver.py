#    Copyright 2013 OpenStack Foundation
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
import base64
import hashlib

from unittest.mock import MagicMock
from unittest.mock import patch

from trove.common import exception
from trove.dns.designate import driver
from trove.dns import driver as base_driver
from trove.tests.unittests import trove_testtools


class DesignateDriverV2Test(trove_testtools.TestCase):

    def setUp(self):
        super(DesignateDriverV2Test, self).setUp()
        self.records = [dict(name='record1.', type='A', data='10.0.0.1',
                             ttl=3600, priority=1,
                             id='11111111-1111-1111-1111-111111111111'),
                        dict(name='record2.', type='CNAME', data='10.0.0.2',
                             ttl=1800, priority=2,
                             id='22222222-2222-2222-2222-222222222222'),
                        dict(name='record3.', type='A', data='10.0.0.3',
                             ttl=3600, priority=1,
                             id='3333333-3333-3333-3333-333333333333')]
        self.mock_client = MagicMock()
        self.create_des_client_patch = patch.object(
            driver, 'create_designate_client', MagicMock(
                return_value=self.mock_client))
        self.create_des_client_mock = self.create_des_client_patch.start()
        self.addCleanup(self.create_des_client_patch.stop)

    def test_create_entry(self):
        dns_driver = driver.DesignateDriverV2()
        zone = driver.DesignateDnsZone(
            id='22222222-2222-2222-2222-222222222222', name='www.trove.com')
        entry = base_driver.DnsEntry(name='www.example.com', content='None',
                                     type='A', ttl=3600, priority=None,
                                     dns_zone=zone)

        dns_driver.create_entry(entry, '1.2.3.4')
        self.mock_client.recordsets.create.assert_called_once_with(
            driver.DNS_DOMAIN_ID, entry.name + '.', entry.type,
            records=['1.2.3.4'])

    def test_delete_entry(self):
        with patch.object(driver.DesignateDriverV2, '_get_records',
                          MagicMock(return_value=self.records)):
            dns_driver = driver.DesignateDriverV2()
            dns_driver.delete_entry('record1', 'A')
            self.mock_client.recordsets.delete(driver.DNS_DOMAIN_ID)

    def test_delete_no_entry(self):
        with patch.object(driver.DesignateDriverV2, '_get_records',
                          MagicMock(return_value=self.records)):
            dns_driver = driver.DesignateDriverV2()
            self.assertRaises(exception.DnsRecordNotFound,
                              dns_driver.delete_entry,
                              'nothere', 'A')
            self.mock_client.recordsets.assert_not_called()


class DesignateInstanceEntryFactoryTest(trove_testtools.TestCase):

    def setUp(self):
        super(DesignateInstanceEntryFactoryTest, self).setUp()

    def tearDown(self):
        super(DesignateInstanceEntryFactoryTest, self).tearDown()

    def test_create_entry(self):
        instance_id = '11111111-2222-3333-4444-555555555555'
        driver.DNS_DOMAIN_ID = '00000000-0000-0000-0000-000000000000'
        driver.DNS_DOMAIN_NAME = 'trove.com'
        driver.DNS_TTL = 3600
        hashed_id = hashlib.md5(instance_id.encode()).digest()
        hashed_id = base64.b32encode(hashed_id)
        hashed_id = hashed_id.decode('ascii')
        hashed_id_concat = hashed_id[:11].lower()
        exp_hostname = ("%s.%s" % (hashed_id_concat, driver.DNS_DOMAIN_NAME))
        factory = driver.DesignateInstanceEntryFactory()
        entry = factory.create_entry(instance_id)
        self.assertEqual(exp_hostname, entry.name)
        self.assertEqual('A', entry.type)
        self.assertEqual(3600, entry.ttl)
        zone = entry.dns_zone
        self.assertEqual(driver.DNS_DOMAIN_NAME, zone.name)
        self.assertEqual(driver.DNS_DOMAIN_ID, zone.id)

    def test_create_entry_ends_with_dot(self):
        instance_id = '11111111-2222-3333-4444-555555555555'
        driver.DNS_DOMAIN_ID = '00000000-0000-0000-0000-000000000000'
        driver.DNS_DOMAIN_NAME = 'trove.com.'
        driver.DNS_TTL = 3600
        hashed_id = hashlib.md5(instance_id.encode()).digest()
        hashed_id = base64.b32encode(hashed_id)
        hashed_id = hashed_id.decode('ascii')
        hashed_id_concat = hashed_id[:11].lower()
        exp_hostname = ("%s.%s" %
                        (hashed_id_concat, driver.DNS_DOMAIN_NAME))[:-1]
        factory = driver.DesignateInstanceEntryFactory()
        entry = factory.create_entry(instance_id)
        self.assertEqual(exp_hostname, entry.name)
