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

import re

import netaddr

from trove.common import cfg
from trove.common.db import models
from trove.common.db.mysql import data as mysql_settings
from trove.common.i18n import _

CONF = cfg.CONF


class MySQLSchema(models.DatastoreSchema):
    """Represents a MySQL database and its properties."""

    # Defaults
    __charset__ = "utf8"
    __collation__ = "utf8_general_ci"
    dbname = re.compile("^[A-Za-z0-9_-]+[\s\?\#\@]*[A-Za-z0-9_-]+$")

    # Complete list of acceptable values
    collation = mysql_settings.collation
    charset = mysql_settings.charset

    def __init__(self, name=None, collate=None, character_set=None,
                 deserializing=False):
        super(MySQLSchema, self).__init__(name=name,
                                          deserializing=deserializing)
        if not deserializing:
            if collate:
                self.collate = collate
            if character_set:
                self.character_set = character_set

    @property
    def _max_schema_name_length(self):
        return 64

    def _is_valid_schema_name(self, value):
        # must match the dbname regex, and
        # cannot contain a '\' character.
        return not any([
            not self.dbname.match(value),
            ("%r" % value).find("\\") != -1
        ])

    @property
    def collate(self):
        """Get the appropriate collate value."""
        if not self._collate and not self._character_set:
            return self.__collation__
        elif not self._collate:
            return self.charset[self._character_set][0]
        else:
            return self._collate

    @collate.setter
    def collate(self, value):
        """Validate the collation and set it."""
        if not value:
            pass
        elif self._character_set:
            if value not in self.charset[self._character_set]:
                msg = (_("%(val)s not a valid collation for charset %(char)s.")
                       % {'val': value, 'char': self._character_set})
                raise ValueError(msg)
            self._collate = value
        else:
            if value not in self.collation:
                raise ValueError(_("'%s' not a valid collation.") % value)
            self._collate = value
            self._character_set = self.collation[value]

    @property
    def character_set(self):
        """Get the appropriate character set value."""
        if not self._character_set:
            return self.__charset__
        else:
            return self._character_set

    @character_set.setter
    def character_set(self, value):
        """Validate the character set and set it."""
        if not value:
            pass
        elif value not in self.charset:
            raise ValueError(_("'%s' not a valid character set.") % value)
        else:
            self._character_set = value

    def verify_dict(self):
        # Also check the collate and character_set values if set, initialize
        # them if not.
        super(MySQLSchema, self).verify_dict()
        if self.__dict__.get('_collate'):
            self.collate = self._collate
        else:
            self._collate = None
        if self.__dict__.get('_character_set'):
            self.character_set = self._character_set
        else:
            self._character_set = None


class MySQLUser(models.DatastoreUser):
    """Represents a MySQL User and its associated properties."""

    not_supported_chars = re.compile("^\s|\s$|'|\"|;|`|,|/|\\\\")

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

    def _is_valid_host_name(self, value):
        if value in [None, "%"]:
            # % is MySQL shorthand for "everywhere". Always permitted.
            # Null host defaults to % anyway.
            return True
        if CONF.hostname_require_valid_ip:
            try:
                # '%' works as a MySQL wildcard, but it is not a valid
                # part of an IPNetwork
                netaddr.IPNetwork(value.replace('%', '1'))
            except (ValueError, netaddr.AddrFormatError):
                return False
            else:
                return True
        else:
            # If it wasn't required, anything else goes.
            return True

    def _build_database_schema(self, name):
        return MySQLSchema(name)

    def deserialize_schema(self, value):
        return MySQLSchema.deserialize(value)

    @property
    def _max_user_name_length(self):
        return 16

    @property
    def schema_model(self):
        return MySQLSchema
