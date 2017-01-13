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

import mock

from trove.common.rpc import serializer
from trove.tests.unittests import trove_testtools


class TestSerializer(trove_testtools.TestCase):

    def setUp(self):
        self.data = 'abcdefghijklmnopqrstuvwxyz'
        self.context = {}
        super(TestSerializer, self).setUp()

    def tearDown(self):
        super(TestSerializer, self).tearDown()

    def test_serialize_1(self):
        base = mock.Mock()
        sz = serializer.TroveSerializer(base=base)
        sz.serialize_entity(self.context, self.data)
        base.serialize_entity.assert_called_with(self.context, self.data)

    def test_serialize_2(self):
        base = mock.Mock()
        sz1 = serializer.TroveSerializer(base=base)
        sz = serializer.TroveSerializer(base=sz1)
        sz.serialize_entity(self.context, self.data)
        base.serialize_entity.assert_called_with(self.context, self.data)

    def test_serialize_3(self):
        base = mock.Mock()
        sz = serializer.TroveSerializer(base=base)
        sz.deserialize_entity(self.context, self.data)
        base.deserialize_entity.assert_called_with(self.context, self.data)

    def test_serialize_4(self):
        base = mock.Mock()
        sz1 = serializer.TroveSerializer(base=base)
        sz = serializer.TroveSerializer(base=sz1)
        sz.deserialize_entity(self.context, self.data)
        base.deserialize_entity.assert_called_with(self.context, self.data)

    def test_serialize_5(self):
        base = mock.Mock()
        sz = serializer.TroveSerializer(base=base)
        sz.serialize_context(self.context)
        base.serialize_context.assert_called_with(self.context)

    def test_serialize_6(self):
        base = mock.Mock()
        sz1 = serializer.TroveSerializer(base=base)
        sz = serializer.TroveSerializer(base=sz1)
        sz.serialize_context(self.context)
        base.serialize_context.assert_called_with(self.context)

    def test_serialize_7(self):
        base = mock.Mock()
        sz = serializer.TroveSerializer(base=base)
        sz.deserialize_context(self.context)
        base.deserialize_context.assert_called_with(self.context)

    def test_serialize_8(self):
        base = mock.Mock()
        sz1 = serializer.TroveSerializer(base=base)
        sz = serializer.TroveSerializer(base=sz1)
        sz.deserialize_context(self.context)
        base.deserialize_context.assert_called_with(self.context)

    def test_serialize_9(self):
        sz = serializer.TroveSerializer(base=None)
        self.assertEqual(sz.serialize_entity(self.context, self.data),
                         self.data)

    def test_serialize_10(self):
        sz = serializer.TroveSerializer(base=None)
        self.assertEqual(sz.deserialize_entity(self.context, self.data),
                         self.data)

    def test_serialize_11(self):
        sz = serializer.TroveSerializer(base=None)
        self.assertEqual(sz.serialize_context(self.context),
                         self.context)

    def test_serialize_12(self):
        sz = serializer.TroveSerializer(base=None)
        self.assertEqual(sz.deserialize_context(self.context),
                         self.context)

    def test_serialize_13(self):
        bz = serializer.TroveSerializer(base=None)
        sz = serializer.TroveSerializer(base=bz)
        self.assertEqual(sz.serialize_entity(self.context, self.data),
                         self.data)

    def test_serialize_14(self):
        bz = serializer.TroveSerializer(base=None)
        sz = serializer.TroveSerializer(base=bz)
        self.assertEqual(sz.deserialize_entity(self.context, self.data),
                         self.data)

    def test_serialize_15(self):
        bz = serializer.TroveSerializer(base=None)
        sz = serializer.TroveSerializer(base=bz)
        self.assertEqual(sz.serialize_context(self.context),
                         self.context)

    def test_serialize_16(self):
        bz = serializer.TroveSerializer(base=None)
        sz = serializer.TroveSerializer(base=bz)
        self.assertEqual(sz.deserialize_context(self.context),
                         self.context)
