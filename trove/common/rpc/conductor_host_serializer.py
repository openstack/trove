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

from trove.common import crypto_utils as cu
from trove.common.rpc import serializer
from trove.instance.models import get_instance_encryption_key

CONF = cfg.CONF


# BUG(1650518): Cleanup in the Pike release
class ConductorHostSerializer(serializer.TroveSerializer):
    def __init__(self, base, *_):
        super(ConductorHostSerializer, self).__init__(base)

    def _serialize_entity(self, ctxt, entity):
        try:
            if ctxt.instance_id is None:
                return entity
        except (ValueError, TypeError):
            return entity

        instance_key = get_instance_encryption_key(ctxt.instance_id)

        estr = jsonutils.dumps(entity)
        return cu.encode_data(cu.encrypt_data(estr, instance_key))

    def _deserialize_entity(self, ctxt, entity):
        try:
            entity = jsonutils.loads(entity)
            instance_id = entity['csz-instance-id']
        except (ValueError, TypeError):
            return entity

        instance_key = get_instance_encryption_key(instance_id)

        estr = cu.decrypt_data(cu.decode_data(entity['entity']),
                               instance_key)
        entity = jsonutils.loads(estr)

        return entity

    def _serialize_context(self, ctxt):
        try:
            if ctxt.instance_id is None:
                return ctxt
        except (ValueError, TypeError):
            return ctxt

        instance_key = get_instance_encryption_key(ctxt.instance_id)

        cstr = jsonutils.dumps(ctxt)
        return {'context': cu.encode_data(cu.encrypt_data(cstr,
                                                          instance_key))}

    def _deserialize_context(self, ctxt):
        try:
            instance_id = ctxt.get('csz-instance-id', None)

            if instance_id is not None:
                instance_key = get_instance_encryption_key(instance_id)

                cstr = cu.decrypt_data(cu.decode_data(ctxt['context']),
                                       instance_key)
                ctxt = jsonutils.loads(cstr)
        except (ValueError, TypeError):
            return ctxt

        ctxt['instance_id'] = instance_id
        return ctxt
