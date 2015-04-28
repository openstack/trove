#    Copyright 2013 OpenStack Foundation
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


from testtools import TestCase
from trove.common.exception import TroveError


class TroveErrorTest(TestCase):

    def test_valid_error_message_format(self):
        error = TroveError("%02d" % 1)
        self.assertEqual("01", error.message)

    def test_invalid_error_message_format(self):
        error = TroveError("test%999999sdb")
        self.assertEqual("test999999sdb", error.message)
