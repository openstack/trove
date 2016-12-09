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

from trove.common.rpc import secure_serializer as ssz
from trove.tests.unittests import trove_testtools


class TestSecureSerializer(trove_testtools.TestCase):

    def setUp(self):
        self.key = 'xuUyAKn5mDANoM5sRxQsb6HGiugWVD'
        self.data = '5rzFfaKU630rRxL1g3c80EHnHDf534'
        self.context = {'fld1': 3, 'fld2': 'abc'}
        super(TestSecureSerializer, self).setUp()

    def tearDown(self):
        super(TestSecureSerializer, self).tearDown()

    def test_sz_nokey_serialize_entity(self):
        sz = ssz.SecureSerializer(base=None, key=None)
        en = sz.serialize_entity(self.context, self.data)
        self.assertEqual(en, self.data)

    def test_sz_nokey_deserialize_entity(self):
        sz = ssz.SecureSerializer(base=None, key=None)
        en = sz.deserialize_entity(self.context, self.data)
        self.assertEqual(en, self.data)

    def test_sz_nokey_serialize_context(self):
        sz = ssz.SecureSerializer(base=None, key=None)
        en = sz.serialize_context(self.context)
        self.assertEqual(en, self.context)

    def test_sz_nokey_deserialize_context(self):
        sz = ssz.SecureSerializer(base=None, key=None)
        en = sz.deserialize_context(self.context)
        self.assertEqual(en, self.context)

    def test_sz_entity(self):
        sz = ssz.SecureSerializer(base=None, key=self.key)
        en = sz.serialize_entity(self.context, self.data)
        self.assertNotEqual(en, self.data)
        self.assertEqual(sz.deserialize_entity(self.context, en),
                         self.data)

    def test_sz_context(self):
        sz = ssz.SecureSerializer(base=None, key=self.key)
        sctxt = sz.serialize_context(self.context)
        self.assertNotEqual(sctxt, self.context)
        self.assertEqual(sz.deserialize_context(sctxt),
                         self.context)
