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

from oslo_config import cfg
from oslo_serialization import jsonutils

from trove.common import crypto_utils as crypto
from trove.common.i18n import _
from trove.common.rpc import serializer

CONF = cfg.CONF


# BUG(1650518): Cleanup in the Pike release
class ConductorGuestSerializer(serializer.TroveSerializer):
    def __init__(self, base, key):
        self._key = key
        super(ConductorGuestSerializer, self).__init__(base)

    def _serialize_entity(self, ctxt, entity):
        if self._key is None:
            return entity

        value = crypto.encode_data(
            crypto.encrypt_data(
                jsonutils.dumps(entity), self._key))

        return jsonutils.dumps({'entity': value, 'csz-instance-id':
                                CONF.guest_id})

    def _deserialize_entity(self, ctxt, entity):
        msg = (_("_deserialize_entity not implemented in "
                 "ConductorGuestSerializer."))
        raise Exception(msg)

    def _serialize_context(self, ctxt):
        if self._key is None:
            return ctxt

        cstr = jsonutils.dumps(ctxt)

        return {'context':
                crypto.encode_data(
                    crypto.encrypt_data(cstr, self._key)),
                'csz-instance-id': CONF.guest_id}

    def _deserialize_context(self, ctxt):
        msg = (_("_deserialize_context not implemented in "
                 "ConductorGuestSerializer."))
        raise Exception(msg)
