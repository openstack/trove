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
from unittest import mock


from trove.common import crypto_utils
from trove.tests.unittests import trove_testtools


class TestEncryptUtils(trove_testtools.TestCase):

    def setUp(self):
        super(TestEncryptUtils, self).setUp()

    def tearDown(self):
        super(TestEncryptUtils, self).tearDown()

    def test_encode_decode_string(self):
        random_data = bytearray(os.urandom(12))
        data = [b'abc', b'numbers01234', b'\x00\xFF\x00\xFF\xFF\x00',
                random_data, 'Unicode:\u20ac']

        for datum in data:
            encoded_data = crypto_utils.encode_data(datum)
            decoded_data = crypto_utils.decode_data(encoded_data)
            if isinstance(datum, str):
                decoded_data = decoded_data.decode('utf-8')
            self. assertEqual(datum, decoded_data,
                              "Encode/decode failed")

    def test_pad_unpad(self):
        for size in range(1, 100):
            data_str = b'a' * size
            padded_str = crypto_utils.pad_for_encryption(
                data_str, crypto_utils.IV_BYTE_COUNT)
            self.assertEqual(0, len(padded_str) % crypto_utils.IV_BYTE_COUNT,
                             "Padding not successful")
            unpadded_str = crypto_utils.unpad_after_decryption(padded_str)
            self.assertEqual(data_str, unpadded_str,
                             "String mangled after pad/unpad")

    def test_encryp_decrypt(self):
        key = 'my_secure_key'
        for size in range(1, 100):
            orig_data = os.urandom(size)
            orig_encoded = crypto_utils.encode_data(orig_data)
            encrypted = crypto_utils.encrypt_data(orig_encoded, key)
            encoded = crypto_utils.encode_data(encrypted)
            decoded = crypto_utils.decode_data(encoded)
            decrypted = crypto_utils.decrypt_data(decoded, key)
            final_decoded = crypto_utils.decode_data(decrypted)

            self.assertEqual(orig_data, final_decoded,
                             "Decrypted data did not match original")

    def test_encrypt(self):
        # test encrypt() with an hardcoded IV
        key = 'my_secure_key'
        salt = b'x' * crypto_utils.IV_BYTE_COUNT

        with mock.patch('os.urandom', return_value=salt):
            for orig_data, expected in (
                # byte string
                (b'Hello World!',
                 'eHh4eHh4eHh4eHh4eHh4eF5RK6VdDrAWl4Th1mNG2eps+VB2BouFRiY2Wa'
                    'P/RRPT'),

                # Unicoded string (encoded to UTF-8)
                ('Unicode:\u20ac',
                 'eHh4eHh4eHh4eHh4eHh4eAMsI5YsrtMNAPJfVF0j9NegXML7OsJ0LuAy66'
                    'LKv5F4'),
            ):
                orig_encoded = crypto_utils.encode_data(orig_data)
                encrypted = crypto_utils.encrypt_data(orig_encoded, key)
                encoded = crypto_utils.encode_data(encrypted)
                self.assertEqual(expected, encoded)

    def test_decrypt(self):
        key = 'my_secure_key'

        for encoded, expected in (
            # byte string: b'Hello World!'
            ('ZUhoNGVIaDRlSGg0ZUhoNL9PmM70hVcQ7j/kYF7Pw+BT7VSfsht0VsCIxy'
                'KNN0NH',
             b'Hello World!'),

            # Unicoded string: 'Unicode:\u20ac'
            ('ZUhoNGVIaDRlSGg0ZUhoNIHZLIuIcQCRwWY7PR2y7JcqoDf4ViqXIfh0uE'
                'Rbg9BA',
             b'Unicode:\xe2\x82\xac'),
        ):
            decoded = crypto_utils.decode_data(encoded)
            decrypted = crypto_utils.decrypt_data(decoded, key)
            final_decoded = crypto_utils.decode_data(decrypted)
            self.assertEqual(expected, final_decoded)
