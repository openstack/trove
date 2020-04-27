# Copyright 2016 Tesora, Inc.
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
#

from unittest import mock

from trove.common import cfg
from trove.common.rpc import conductor_guest_serializer as gsz
from trove.common.rpc import conductor_host_serializer as hsz

from trove.tests.unittests import trove_testtools


CONF = cfg.CONF


class FakeInstance(object):
    def __init__(self):
        self.uuid = 'a3af1652-686a-4574-a916-2ef7e85136e5'

    @property
    def key(self):
        return 'mo79Y86Bp3bzQDWR31ihhVGfLBmeac'


class FakeContext(object):
    def __init__(self, instance_id=None, fields=None):
        self.instance_id = instance_id
        self.fields = fields


class TestConductorSerializer(trove_testtools.TestCase):

    def setUp(self):
        self.uuid = 'a3af1652-686a-4574-a916-2ef7e85136e5'
        self.key = 'mo79Y86Bp3bzQDWR31ihhVGfLBmeac'
        self.data = 'ELzWd81qtgcj2Gxc1ipbh0HgbvHGrgptDj3n4GNMBN0F2WtNdr'
        self.context = {'a': 'ij2J8AJLyz0rDqbjxy4jPVINhnK2jsBGpWRKIe3tUnUD',
                        'b': 32,
                        'c': {'a': 21, 'b': 22}}
        self.old_guest_id = gsz.CONF.guest_id
        gsz.CONF.guest_id = self.uuid
        super(TestConductorSerializer, self).setUp()

    def tearDown(self):
        gsz.CONF.guest_id = self.old_guest_id
        super(TestConductorSerializer, self).tearDown()

    def test_gsz_serialize_entity_nokey(self):
        sz = gsz.ConductorGuestSerializer(None, None)
        self.assertEqual(sz.serialize_entity(self.context, self.data),
                         self.data)

    def test_gsz_serialize_context_nokey(self):
        sz = gsz.ConductorGuestSerializer(None, None)
        self.assertEqual(sz.serialize_context(self.context),
                         self.context)

    @mock.patch('trove.common.rpc.conductor_host_serializer.'
                'get_instance_encryption_key',
                return_value='mo79Y86Bp3bzQDWR31ihhVGfLBmeac')
    def test_hsz_serialize_entity_nokey_noinstance(self, _):
        sz = hsz.ConductorHostSerializer(None, None)
        ctxt = FakeContext(instance_id=None)
        self.assertEqual(sz.serialize_entity(ctxt, self.data),
                         self.data)

    @mock.patch('trove.common.rpc.conductor_host_serializer.'
                'get_instance_encryption_key',
                return_value='mo79Y86Bp3bzQDWR31ihhVGfLBmeac')
    def test_hsz_serialize_context_nokey_noinstance(self, _):
        sz = hsz.ConductorHostSerializer(None, None)
        ctxt = FakeContext(instance_id=None)
        self.assertEqual(sz.serialize_context(ctxt), ctxt)

    @mock.patch('trove.common.rpc.conductor_host_serializer.'
                'get_instance_encryption_key',
                return_value='mo79Y86Bp3bzQDWR31ihhVGfLBmeac')
    def test_conductor_entity(self, _):
        guestsz = gsz.ConductorGuestSerializer(None, self.key)
        hostsz = hsz.ConductorHostSerializer(None, None)
        encrypted_entity = guestsz.serialize_entity(self.context, self.data)
        self.assertNotEqual(encrypted_entity, self.data)
        entity = hostsz.deserialize_entity(self.context, encrypted_entity)
        self.assertEqual(entity, self.data)

    @mock.patch('trove.common.rpc.conductor_host_serializer.'
                'get_instance_encryption_key',
                return_value='mo79Y86Bp3bzQDWR31ihhVGfLBmeac')
    def test_conductor_context(self, _):
        guestsz = gsz.ConductorGuestSerializer(None, self.key)
        hostsz = hsz.ConductorHostSerializer(None, None)
        encrypted_context = guestsz.serialize_context(self.context)
        self.assertNotEqual(encrypted_context, self.context)
        context = hostsz.deserialize_context(encrypted_context)
        self.assertEqual(context.get('instance_id'), self.uuid)
        context.pop('instance_id')
        self.assertDictEqual(context, self.context)
