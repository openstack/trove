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

import os

from trove.common import stream_codecs
from trove.tests.unittests import trove_testtools


class TestStreamCodecs(trove_testtools.TestCase):

    def setUp(self):
        super(TestStreamCodecs, self).setUp()

    def tearDown(self):
        super(TestStreamCodecs, self).tearDown()

    def test_serialize_deserialize_base64codec(self):
        random_data = bytearray(os.urandom(12))
        data = [b'abc',
                b'numbers01234',
                b'non-ascii:\xe9\xff',
                random_data]

        codec = stream_codecs.Base64Codec()
        for datum in data:
            serialized_data = codec.serialize(datum)
            deserialized_data = codec.deserialize(serialized_data)
            self. assertEqual(datum, deserialized_data,
                              "Serialize/Deserialize failed")
