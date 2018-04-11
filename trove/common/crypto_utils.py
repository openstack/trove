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

import hashlib
import os
from oslo_utils import encodeutils
import random
import six
import string

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import modes
from trove.common import stream_codecs


IV_BYTE_COUNT = 16
_CRYPT_BACKEND = None


def _get_cipher(key, iv):
    global _CRYPT_BACKEND
    if not _CRYPT_BACKEND:
        _CRYPT_BACKEND = default_backend()

    return Cipher(algorithms.AES(key), modes.CBC(iv),
                  backend=_CRYPT_BACKEND)


def _encrypt(key, iv, data):
    encryptor = _get_cipher(key, iv).encryptor()
    return encryptor.update(data) + encryptor.finalize()


def _decrypt(key, iv, data):
    decryptor = _get_cipher(key, iv).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def encode_data(data):
    # NOTE(zhaochao) No need to encoding string object any more,
    # as Base64Codec is now using oslo_serialization.base64 which
    # could take care of this.
    return stream_codecs.Base64Codec().serialize(data)


def decode_data(data):
    return stream_codecs.Base64Codec().deserialize(data)


# Pad the data string to an multiple of pad_size
def pad_for_encryption(data, pad_size=IV_BYTE_COUNT):
    pad_count = pad_size - (len(data) % pad_size)
    return data + six.int2byte(pad_count) * pad_count


# Unpad the data string by stripping off excess characters
def unpad_after_decryption(data):
    return data[:len(data) - six.indexbytes(data, -1)]


def encrypt_data(data, key, iv_byte_count=IV_BYTE_COUNT):
    data = encodeutils.to_utf8(data)
    key = encodeutils.to_utf8(key)
    md5_key = encodeutils.safe_encode(hashlib.md5(key).hexdigest())
    iv = os.urandom(iv_byte_count)
    iv = iv[:iv_byte_count]
    data = pad_for_encryption(data, iv_byte_count)
    encrypted = _encrypt(md5_key, bytes(iv), data)
    return iv + encrypted


def decrypt_data(data, key, iv_byte_count=IV_BYTE_COUNT):
    key = encodeutils.to_utf8(key)
    md5_key = encodeutils.safe_encode(hashlib.md5(key).hexdigest())
    iv = data[:iv_byte_count]
    decrypted = _decrypt(md5_key, bytes(iv), bytes(data[iv_byte_count:]))
    return unpad_after_decryption(decrypted)


def generate_random_key(length=32, chars=None):
    chars = chars if chars else (string.ascii_uppercase +
                                 string.ascii_lowercase + string.digits)
    return ''.join(random.choice(chars) for _ in range(length))
