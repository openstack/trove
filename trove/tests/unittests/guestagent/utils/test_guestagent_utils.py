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

from unittest import TestCase

from trove.common import exception
from trove.guestagent.common.guestagent_utils import (
    prevent_major_version_upgrade,
)


class TestPreventMajorVersionUpgrade(TestCase):

    def test_minor_version_upgrade_allowed(self):
        allowed_versions = [
            ('17', '17'),
            ('17.1', '17.2'),
            ('5.7.39', '5.7.40'),
        ]

        for current, target in allowed_versions:
            prevent_major_version_upgrade(current, target)

    def test_major_version_upgrade_forbidden(self):
        forbidden_versions = [
            ('17.1', '18.1'),
            ('5.7.40', '8.0'),
        ]

        for current, target in forbidden_versions:
            self.assertRaises(
                exception.TroveError,
                prevent_major_version_upgrade,
                current,
                target
            )
