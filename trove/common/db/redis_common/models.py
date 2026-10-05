# Copyright 2026 PS Cloud Services
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
import re

from trove.common import cfg
from trove.common.db import models

CONF = cfg.CONF


class RedisCommonUser(models.DatastoreUser):
    """Represents a Redis-family ACL user."""

    not_supported_chars = re.compile(r"""\s|'|\"|;|`|,|/|\\""")

    def _is_valid_string(self, value):
        if (not value or
                self.not_supported_chars.search(value) or
                ("%r" % value).find("\\") != -1):
            return False
        else:
            return True

    def _is_valid_user_name(self, value):
        return self._is_valid_string(value)

    def _is_valid_password(self, value):
        return self._is_valid_string(value)


class RedisCommonSchema(models.DatastoreSchema):
    pass
