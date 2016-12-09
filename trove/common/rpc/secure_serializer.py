# Copyright 2016 Tesora, Inc.
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_serialization import jsonutils

from trove.common import crypto_utils as cu
from trove.common.rpc import serializer


# BUG(1650518): Cleanup in the Pike release
class SecureSerializer(serializer.TroveSerializer):
    def __init__(self, base, key):
        self._key = key
        super(SecureSerializer, self).__init__(base)

    def _serialize_entity(self, ctxt, entity):
        if self._key is None:
            return entity

        estr = jsonutils.dumps(entity)
        return cu.encode_data(cu.encrypt_data(estr, self._key))

    def _deserialize_entity(self, ctxt, entity):
        try:
            if self._key is not None:
                estr = cu.decrypt_data(cu.decode_data(entity), self._key)
                entity = jsonutils.loads(estr)
        except (ValueError, TypeError):
            return entity

        return entity

    def _serialize_context(self, ctxt):
        if self._key is None:
            return ctxt

        cstr = jsonutils.dumps(ctxt)
        return {'context': cu.encode_data(cu.encrypt_data(cstr, self._key))}

    def _deserialize_context(self, ctxt):
        try:
            if self._key is not None:
                cstr = cu.decrypt_data(cu.decode_data(ctxt['context']),
                                       self._key)
                ctxt = jsonutils.loads(cstr)
        except (ValueError, TypeError):
            return ctxt

        return ctxt
