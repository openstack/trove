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

from designateclient.v1.domains import Domain
from designateclient.v1.records import Record
from mock import MagicMock
from mock import patch

from trove.dns.designate import driver
from trove.tests.unittests import trove_testtools


class DesignateObjectConverterTest(trove_testtools.TestCase):

    def setUp(self):
        super(DesignateObjectConverterTest, self).setUp()

    def tearDown(self):
        super(DesignateObjectConverterTest, self).tearDown()

    def test_convert_domain_to_zone(self):
        name = 'www.example.com'
        id = '39413651-3b9e-41f1-a4df-e47d5e9f67be'
        email = 'john.smith@openstack.com'
        domain = Domain(name=name, id=id, email=email)
        converter = driver.DesignateObjectConverter()
        converted_domain = converter.domain_to_zone(domain)
        self.assertEqual(name, converted_domain.name)
        self.assertEqual(id, converted_domain.id)

    def test_convert_record_to_entry(self):
        name = 'test.example.com'
        id = '4f3439ef-fc8b-4098-a1aa-a66ed01102b9'
        domain_id = '39413651-3b9e-41f1-a4df-e47d5e9f67be'
        domain_name = 'example.com'
        type = 'CNAME'
        data = '127.0.0.1'
        ttl = 3600
        priority = 1
        zone = driver.DesignateDnsZone(domain_id, domain_name)
        record = Record(name=name, id=id, domain_id=domain_id, type=type,
                        data=data, priority=priority, ttl=ttl)
        converter = driver.DesignateObjectConverter()
        converted_record = converter.record_to_entry(record, zone)
        self.assertEqual(name, converted_record.name)
        self.assertEqual(data, converted_record.content)
        self.assertEqual(type, converted_record.type)
        self.assertEqual(priority, converted_record.priority)
        self.assertEqual(ttl, converted_record.ttl)
        self.assertEqual(zone, converted_record.dns_zone)


class DesignateDriverTest(trove_testtools.TestCase):

    def setUp(self):
        super(DesignateDriverTest, self).setUp()
        self.domains = [Domain(name='www.example.com',
                               id='11111111-1111-1111-1111-111111111111',
                               email='test@example.com'),
                        Domain(name='www.trove.com',
                               id='22222222-2222-2222-2222-222222222222',
                               email='test@trove.com'),
                        Domain(name='www.openstack.com',
                               id='33333333-3333-3333-3333-333333333333',
                               email='test@openstack.com')]
        self.records = [Record(name='record1', type='A', data='10.0.0.1',
                               ttl=3600, priority=1),
                        Record(name='record2', type='CNAME', data='10.0.0.2',
                               ttl=1800, priority=2),
                        Record(name='record3', type='A', data='10.0.0.3',
                               ttl=3600, priority=1)]
        self.create_des_client_patch = patch.object(
            driver, 'create_designate_client', MagicMock(return_value=None))
        self.create_des_client_mock = self.create_des_client_patch.start()
        self.addCleanup(self.create_des_client_patch.stop)

    def tearDown(self):
        super(DesignateDriverTest, self).tearDown()

    def test_get_entries_by_name(self):
        zone = driver.DesignateDnsZone('123', 'www.example.com')
        with patch.object(driver.DesignateDriver, '_get_records',
                          MagicMock(return_value=self.records)):
            dns_driver = driver.DesignateDriver()
            entries = dns_driver.get_entries_by_name('record2', zone)
            self.assertEqual(1, len(entries), 'More than one record found')
            entry = entries[0]
            self.assertEqual('record2', entry.name)
            self.assertEqual('CNAME', entry.type)
            self.assertEqual('10.0.0.2', entry.content)
            self.assertEqual(1800, entry.ttl)
            self.assertEqual(2, entry.priority)
            zone = entry.dns_zone
            self.assertEqual('123', zone.id)
            self.assertEqual('www.example.com', zone.name)

    def test_get_entries_by_name_not_found(self):
        zone = driver.DesignateDnsZone('123', 'www.example.com')
        with patch.object(driver.DesignateDriver, '_get_records',
                          MagicMock(return_value=self.records)):
            dns_driver = driver.DesignateDriver()
            entries = dns_driver.get_entries_by_name('record_not_found', zone)
            self.assertEqual(0, len(entries), 'Some records were returned')

    def test_get_entries_by_content(self):
        zone = driver.DesignateDnsZone('123', 'www.example.com')
        with patch.object(driver.DesignateDriver, '_get_records',
                          MagicMock(return_value=self.records)):
            dns_driver = driver.DesignateDriver()
            entries = dns_driver.get_entries_by_content('10.0.0.1', zone)
            self.assertEqual(1, len(entries), 'More than one record found')
            entry = entries[0]
            self.assertEqual('record1', entry.name)
            self.assertEqual('A', entry.type)
            self.assertEqual('10.0.0.1', entry.content)
            self.assertEqual(3600, entry.ttl)
            self.assertEqual(1, entry.priority)
            zone = entry.dns_zone
            self.assertEqual('123', zone.id)
            self.assertEqual('www.example.com', zone.name)

    def test_get_entries_by_content_not_found(self):
        zone = driver.DesignateDnsZone('123', 'www.example.com')
        with patch.object(driver.DesignateDriver, '_get_records',
                          MagicMock(return_value=self.records)):
            dns_driver = driver.DesignateDriver()
            entries = dns_driver.get_entries_by_content('127.0.0.1', zone)
            self.assertEqual(0, len(entries), 'Some records were returned')

    def test_get_dnz_zones(self):
        client = MagicMock()
        self.create_des_client_mock.return_value = client
        client.domains.list = MagicMock(return_value=self.domains)
        dns_driver = driver.DesignateDriver()
        zones = dns_driver.get_dns_zones()
        self.assertEqual(3, len(zones))
        for x in range(0, 3):
            self.assertDomainsAreEqual(self.domains[x], zones[x])

    def test_get_dnz_zones_by_name(self):
        client = MagicMock()
        self.create_des_client_mock.return_value = client
        client.domains.list = MagicMock(return_value=self.domains)
        dns_driver = driver.DesignateDriver()
        zones = dns_driver.get_dns_zones('www.trove.com')
        self.assertEqual(1, len(zones))
        self.assertDomainsAreEqual(self.domains[1], zones[0])

    def test_get_dnz_zones_not_found(self):
        client = MagicMock()
        self.create_des_client_mock.return_value = client
        client.domains.list = MagicMock(return_value=self.domains)
        dns_driver = driver.DesignateDriver()
        zones = dns_driver.get_dns_zones('www.notfound.com')
        self.assertEqual(0, len(zones))

    def assertDomainsAreEqual(self, expected, actual):
        self.assertEqual(expected.name, actual.name)
        self.assertEqual(expected.id, actual.id)


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
        hashed_id = base64.b32encode(hashlib.md5(instance_id).digest())
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
        hashed_id = base64.b32encode(hashlib.md5(instance_id).digest())
        hashed_id_concat = hashed_id[:11].lower()
        exp_hostname = ("%s.%s" %
                        (hashed_id_concat, driver.DNS_DOMAIN_NAME))[:-1]
        factory = driver.DesignateInstanceEntryFactory()
        entry = factory.create_entry(instance_id)
        self.assertEqual(exp_hostname, entry.name)
