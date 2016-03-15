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

from Crypto import Random

from trove.common import crypto_utils
from trove.tests.unittests import trove_testtools


class TestEncryptUtils(trove_testtools.TestCase):

    def setUp(self):
        super(TestEncryptUtils, self).setUp()

    def tearDown(self):
        super(TestEncryptUtils, self).tearDown()

    def test_encode_decode_string(self):
        random_data = bytearray(Random.new().read(12))
        data = ['abc', 'numbers01234', '\x00\xFF\x00\xFF\xFF\x00', random_data]

        for datum in data:
            encoded_data = crypto_utils.encode_data(datum)
            decoded_data = crypto_utils.decode_data(encoded_data)
            self. assertEqual(datum, decoded_data,
                              "Encode/decode failed")

    def test_pad_unpad(self):
        for size in range(1, 100):
            data_str = 'a' * size
            padded_str = crypto_utils.pad_for_encryption(
                data_str, crypto_utils.IV_BIT_COUNT)
            self.assertEqual(0, len(padded_str) % crypto_utils.IV_BIT_COUNT,
                             "Padding not successful")
            unpadded_str = crypto_utils.unpad_after_decryption(padded_str)
            self.assertEqual(data_str, unpadded_str,
                             "String mangled after pad/unpad")

    def test_encryp_decrypt(self):
        key = 'my_secure_key'
        for size in range(1, 100):
            orig_data = Random.new().read(size)
            orig_encoded = crypto_utils.encode_data(orig_data)
            encrypted = crypto_utils.encrypt_data(orig_encoded, key)
            encoded = crypto_utils.encode_data(encrypted)
            decoded = crypto_utils.decode_data(encoded)
            decrypted = crypto_utils.decrypt_data(decoded, key)
            final_decoded = crypto_utils.decode_data(decrypted)

            self.assertEqual(orig_data, final_decoded,
                             "Decrypted data did not match original")
