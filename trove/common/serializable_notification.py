#    Copyright 2015 Tesora Inc.
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

from trove.common.utils import import_class


class SerializableNotification(object):

    @staticmethod
    def serialize(context, notification):
        serialized = notification.serialize(context)
        serialized['notification_classname'] = (
            notification.__module__ + "." + type(notification).__name__)
        return serialized

    @staticmethod
    def deserialize(context, serialized):
        classname = serialized.pop('notification_classname')
        notification_class = import_class(classname)
        return notification_class(context, **serialized)
