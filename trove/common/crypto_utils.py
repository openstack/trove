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

# Encryption/decryption handling

from Crypto.Cipher import AES
from Crypto import Random
import hashlib

from trove.common import stream_codecs


IV_BIT_COUNT = 16


def encode_data(data):
    return stream_codecs.Base64Codec().serialize(data)


def decode_data(data):
    return stream_codecs.Base64Codec().deserialize(data)


# Pad the data string to an multiple of pad_size
def pad_for_encryption(data, pad_size=IV_BIT_COUNT):
    pad_count = pad_size - (len(data) % pad_size)
    return data + chr(pad_count) * pad_count


# Unpad the data string by stripping off excess characters
def unpad_after_decryption(data):
    return data[:len(data) - ord(data[-1])]


def encrypt_data(data, key, iv_bit_count=IV_BIT_COUNT):
    md5_key = hashlib.md5(key).hexdigest()
    iv = Random.new().read(iv_bit_count)[:iv_bit_count]
    aes = AES.new(md5_key, AES.MODE_CBC, iv)
    data = pad_for_encryption(data, iv_bit_count)
    encrypted = aes.encrypt(data)
    return iv + encrypted


def decrypt_data(data, key, iv_bit_count=IV_BIT_COUNT):
    md5_key = hashlib.md5(key).hexdigest()
    iv = data[:iv_bit_count]
    aes = AES.new(md5_key, AES.MODE_CBC, bytes(iv))
    decrypted = aes.decrypt(bytes(data[iv_bit_count:]))
    return unpad_after_decryption(decrypted)
