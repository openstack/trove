# Copyright 2014 OpenStack Foundation
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

from trove.common.clients import guest_client


class UpgradeMessageSender(object):
    """
    This class handles the business logic for sending
    an rpc message to the guest
    """

    @staticmethod
    def create(context, instance_id, instance_version, location,
               metadata=None):

        instance_id = UpgradeMessageSender._validate(instance_id, 36)

        if instance_version:
            instance_version = UpgradeMessageSender._validate(
                instance_version, 255)

        if location:
            location = UpgradeMessageSender._validate(location, 255)

        def _create_resources():
            guest_client(context, instance_id).upgrade(
                instance_version, location, metadata)
        return _create_resources

    @staticmethod
    def _validate(s, max_length):
        if s is None:
            raise ValueError()
        s = s.strip()
        length = len(s)
        if length < 1 or length > max_length:
            raise ValueError()
        return s
