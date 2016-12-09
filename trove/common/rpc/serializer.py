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

import oslo_messaging as messaging
from osprofiler import profiler

from trove.common.context import TroveContext


class TroveSerializer(messaging.Serializer):
    """The Trove serializer class that handles class inheritence and base
       serializers.
    """

    def __init__(self, base):
        self._base = base

    def _serialize_entity(self, context, entity):
        return entity

    def serialize_entity(self, context, entity):
        if self._base:
            entity = self._base.serialize_entity(context, entity)

        return self._serialize_entity(context, entity)

    def _deserialize_entity(self, context, entity):
        return entity

    def deserialize_entity(self, context, entity):
        entity = self._deserialize_entity(context, entity)

        if self._base:
            entity = self._base.deserialize_entity(context, entity)

        return entity

    def _serialize_context(self, context):
        return context

    def serialize_context(self, context):
        if self._base:
            context = self._base.serialize_context(context)

        return self._serialize_context(context)

    def _deserialize_context(self, context):
        return context

    def deserialize_context(self, context):
        context = self._deserialize_context(context)

        if self._base:
            context = self._base.deserialize_context(context)

        return context


class TroveRequestContextSerializer(TroveSerializer):
    def _serialize_context(self, context):
        _context = context.to_dict()
        prof = profiler.get()
        if prof:
            trace_info = {
                "hmac_key": prof.hmac_key,
                "base_id": prof.get_base_id(),
                "parent_id": prof.get_id()
            }
            _context.update({"trace_info": trace_info})
        return _context

    def _deserialize_context(self, context):
        trace_info = context.pop("trace_info", None)
        if trace_info:
            profiler.init(**trace_info)
        return TroveContext.from_dict(context)
