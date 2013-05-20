# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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
import string

from reddwarf.common import cfg

CONF = cfg.CONF


class Base(object):
    def serialize(self):
        return self.__dict__

    def deserialize(self, o):
        self.__dict__ = o


class MySQLDatabase(Base):
    """Represents a Database and its properties"""

    _ignore_dbs = CONF.ignore_dbs

    # Defaults
    __charset__ = "utf8"
    __collation__ = "utf8_general_ci"
    dbname = re.compile("^[A-Za-z0-9_-]+[\s\?\#\@]*[A-Za-z0-9_-]+$")

    # Complete list of acceptable values
    charset = {"big5": ["big5_chinese_ci", "big5_bin"],
               "dec8": ["dec8_swedish_ci", "dec8_bin"],
               "cp850": ["cp850_general_ci", "cp850_bin"],
               "hp8": ["hp8_english_ci", "hp8_bin"],
               "koi8r": ["koi8r_general_ci", "koi8r_bin"],
               "latin1": ["latin1_swedish_ci",
                          "latin1_german1_ci",
                          "latin1_danish_ci",
                          "latin1_german2_ci",
                          "latin1_bin",
                          "latin1_general_ci",
                          "latin1_general_cs",
                          "latin1_spanish_ci"],
               "latin2": ["latin2_general_ci",
                          "latin2_czech_cs",
                          "latin2_hungarian_ci",
                          "latin2_croatian_ci",
                          "latin2_bin"],
               "swe7": ["swe7_swedish_ci", "swe7_bin"],
               "ascii": ["ascii_general_ci", "ascii_bin"],
               "ujis": ["ujis_japanese_ci", "ujis_bin"],
               "sjis": ["sjis_japanese_ci", "sjis_bin"],
               "hebrew": ["hebrew_general_ci", "hebrew_bin"],
               "tis620": ["tis620_thai_ci", "tis620_bin"],
               "euckr": ["euckr_korean_ci", "euckr_bin"],
               "koi8u": ["koi8u_general_ci", "koi8u_bin"],
               "gb2312": ["gb2312_chinese_ci", "gb2312_bin"],
               "greek": ["greek_general_ci", "greek_bin"],
               "cp1250": ["cp1250_general_ci",
                          "cp1250_czech_cs",
                          "cp1250_croatian_ci",
                          "cp1250_bin",
                          "cp1250_polish_ci"],
               "gbk": ["gbk_chinese_ci", "gbk_bin"],
               "latin5": ["latin5_turkish_ci", "latin5_bin"],
               "armscii8": ["armscii8_general_ci", "armscii8_bin"],
               "utf8": ["utf8_general_ci",
                        "utf8_bin",
                        "utf8_unicode_ci",
                        "utf8_icelandic_ci",
                        "utf8_latvian_ci",
                        "utf8_romanian_ci",
                        "utf8_slovenian_ci",
                        "utf8_polish_ci",
                        "utf8_estonian_ci",
                        "utf8_spanish_ci",
                        "utf8_swedish_ci",
                        "utf8_turkish_ci",
                        "utf8_czech_ci",
                        "utf8_danish_ci",
                        "utf8_lithuanian_ci",
                        "utf8_slovak_ci",
                        "utf8_spanish2_ci",
                        "utf8_roman_ci",
                        "utf8_persian_ci",
                        "utf8_esperanto_ci",
                        "utf8_hungarian_ci"],
               "ucs2": ["ucs2_general_ci",
                        "ucs2_bin",
                        "ucs2_unicode_ci",
                        "ucs2_icelandic_ci",
                        "ucs2_latvian_ci",
                        "ucs2_romanian_ci",
                        "ucs2_slovenian_ci",
                        "ucs2_polish_ci",
                        "ucs2_estonian_ci",
                        "ucs2_spanish_ci",
                        "ucs2_swedish_ci",
                        "ucs2_turkish_ci",
                        "ucs2_czech_ci",
                        "ucs2_danish_ci",
                        "ucs2_lithuanian_ci",
                        "ucs2_slovak_ci",
                        "ucs2_spanish2_ci",
                        "ucs2_roman_ci",
                        "ucs2_persian_ci",
                        "ucs2_esperanto_ci",
                        "ucs2_hungarian_ci"],
               "cp866": ["cp866_general_ci", "cp866_bin"],
               "keybcs2": ["keybcs2_general_ci", "keybcs2_bin"],
               "macce": ["macce_general_ci", "macce_bin"],
               "macroman": ["macroman_general_ci", "macroman_bin"],
               "cp852": ["cp852_general_ci", "cp852_bin"],
               "latin7": ["latin7_general_ci",
                          "latin7_estonian_cs",
                          "latin7_general_cs",
                          "latin7_bin"],
               "cp1251": ["cp1251_general_ci",
                          "cp1251_bulgarian_ci",
                          "cp1251_ukrainian_ci",
                          "cp1251_bin",
                          "cp1251_general_cs"],
               "cp1256": ["cp1256_general_ci", "cp1256_bin"],
               "cp1257": ["cp1257_general_ci",
                          "cp1257_lithuanian_ci",
                          "cp1257_bin"],
               "binary": ["binary"],
               "geostd8": ["geostd8_general_ci", "geostd8_bin"],
               "cp932": ["cp932_japanese_ci", "cp932_bin"],
               "eucjpms": ["eucjpms_japanese_ci", "eucjpms_bin"]}

    collation = {"big5_chinese_ci": "big5",
                 "big5_bin": "big5",
                 "dec8_swedish_ci": "dec8",
                 "dec8_bin": "dec8",
                 "cp850_general_ci": "cp850",
                 "cp850_bin": "cp850",
                 "hp8_english_ci": "hp8",
                 "hp8_bin": "hp8",
                 "koi8r_general_ci": "koi8r",
                 "koi8r_bin": "koi8r",
                 "latin1_german1_ci": "latin1",
                 "latin1_swedish_ci": "latin1",
                 "latin1_danish_ci": "latin1",
                 "latin1_german2_ci": "latin1",
                 "latin1_bin": "latin1",
                 "latin1_general_ci": "latin1",
                 "latin1_general_cs": "latin1",
                 "latin1_spanish_ci": "latin1",
                 "latin2_czech_cs": "latin2",
                 "latin2_general_ci": "latin2",
                 "latin2_hungarian_ci": "latin2",
                 "latin2_croatian_ci": "latin2",
                 "latin2_bin": "latin2",
                 "swe7_swedish_ci": "swe7",
                 "swe7_bin": "swe7",
                 "ascii_general_ci": "ascii",
                 "ascii_bin": "ascii",
                 "ujis_japanese_ci": "ujis",
                 "ujis_bin": "ujis",
                 "sjis_japanese_ci": "sjis",
                 "sjis_bin": "sjis",
                 "hebrew_general_ci": "hebrew",
                 "hebrew_bin": "hebrew",
                 "tis620_thai_ci": "tis620",
                 "tis620_bin": "tis620",
                 "euckr_korean_ci": "euckr",
                 "euckr_bin": "euckr",
                 "koi8u_general_ci": "koi8u",
                 "koi8u_bin": "koi8u",
                 "gb2312_chinese_ci": "gb2312",
                 "gb2312_bin": "gb2312",
                 "greek_general_ci": "greek",
                 "greek_bin": "greek",
                 "cp1250_general_ci": "cp1250",
                 "cp1250_czech_cs": "cp1250",
                 "cp1250_croatian_ci": "cp1250",
                 "cp1250_bin": "cp1250",
                 "cp1250_polish_ci": "cp1250",
                 "gbk_chinese_ci": "gbk",
                 "gbk_bin": "gbk",
                 "latin5_turkish_ci": "latin5",
                 "latin5_bin": "latin5",
                 "armscii8_general_ci": "armscii8",
                 "armscii8_bin": "armscii8",
                 "utf8_general_ci": "utf8",
                 "utf8_bin": "utf8",
                 "utf8_unicode_ci": "utf8",
                 "utf8_icelandic_ci": "utf8",
                 "utf8_latvian_ci": "utf8",
                 "utf8_romanian_ci": "utf8",
                 "utf8_slovenian_ci": "utf8",
                 "utf8_polish_ci": "utf8",
                 "utf8_estonian_ci": "utf8",
                 "utf8_spanish_ci": "utf8",
                 "utf8_swedish_ci": "utf8",
                 "utf8_turkish_ci": "utf8",
                 "utf8_czech_ci": "utf8",
                 "utf8_danish_ci": "utf8",
                 "utf8_lithuanian_ci": "utf8",
                 "utf8_slovak_ci": "utf8",
                 "utf8_spanish2_ci": "utf8",
                 "utf8_roman_ci": "utf8",
                 "utf8_persian_ci": "utf8",
                 "utf8_esperanto_ci": "utf8",
                 "utf8_hungarian_ci": "utf8",
                 "ucs2_general_ci": "ucs2",
                 "ucs2_bin": "ucs2",
                 "ucs2_unicode_ci": "ucs2",
                 "ucs2_icelandic_ci": "ucs2",
                 "ucs2_latvian_ci": "ucs2",
                 "ucs2_romanian_ci": "ucs2",
                 "ucs2_slovenian_ci": "ucs2",
                 "ucs2_polish_ci": "ucs2",
                 "ucs2_estonian_ci": "ucs2",
                 "ucs2_spanish_ci": "ucs2",
                 "ucs2_swedish_ci": "ucs2",
                 "ucs2_turkish_ci": "ucs2",
                 "ucs2_czech_ci": "ucs2",
                 "ucs2_danish_ci": "ucs2",
                 "ucs2_lithuanian_ci": "ucs2",
                 "ucs2_slovak_ci": "ucs2",
                 "ucs2_spanish2_ci": "ucs2",
                 "ucs2_roman_ci": "ucs2",
                 "ucs2_persian_ci": "ucs2",
                 "ucs2_esperanto_ci": "ucs2",
                 "ucs2_hungarian_ci": "ucs2",
                 "cp866_general_ci": "cp866",
                 "cp866_bin": "cp866",
                 "keybcs2_general_ci": "keybcs2",
                 "keybcs2_bin": "keybcs2",
                 "macce_general_ci": "macce",
                 "macce_bin": "macce",
                 "macroman_general_ci": "macroman",
                 "macroman_bin": "macroman",
                 "cp852_general_ci": "cp852",
                 "cp852_bin": "cp852",
                 "latin7_estonian_cs": "latin7",
                 "latin7_general_ci": "latin7",
                 "latin7_general_cs": "latin7",
                 "latin7_bin": "latin7",
                 "cp1251_bulgarian_ci": "cp1251",
                 "cp1251_ukrainian_ci": "cp1251",
                 "cp1251_bin": "cp1251",
                 "cp1251_general_ci": "cp1251",
                 "cp1251_general_cs": "cp1251",
                 "cp1256_general_ci": "cp1256",
                 "cp1256_bin": "cp1256",
                 "cp1257_lithuanian_ci": "cp1257",
                 "cp1257_bin": "cp1257",
                 "cp1257_general_ci": "cp1257",
                 "binary": "binary",
                 "geostd8_general_ci": "geostd8",
                 "geostd8_bin": "geostd8",
                 "cp932_japanese_ci": "cp932",
                 "cp932_bin": "cp932",
                 "eucjpms_japanese_ci": "eucjpms",
                 "eucjpms_bin": "eucjpms"}

    def __init__(self):
        self._name = None
        self._collate = None
        self._character_set = None

    @property
    def name(self):
        return self._name

    def _is_valid(self, value):
        return value.lower() not in self._ignore_dbs

    @name.setter
    def name(self, value):
        if any([not value,
                not self._is_valid(value),
                not self.dbname.match(value),
                string.find("%r" % value, "\\") != -1]):
            raise ValueError("'%s' is not a valid database name" % value)
        elif len(value) > 64:
            msg = "Database name '%s' is too long. Max length = 64"
            raise ValueError(msg % value)
        else:
            self._name = value

    @property
    def collate(self):
        """Get the appropriate collate value"""
        if not self._collate and not self._character_set:
            return self.__collation__
        elif not self._collate:
            return self.charset[self._character_set][0]
        else:
            return self._collate

    @collate.setter
    def collate(self, value):
        """Validate the collation and set it"""
        if not value:
            pass
        elif self._character_set:
            if not value in self.charset[self._character_set]:
                msg = "'%s' not a valid collation for charset '%s'"
                raise ValueError(msg % (value, self._character_set))
            self._collate = value
        else:
            if not value in self.collation:
                raise ValueError("'%s' not a valid collation" % value)
            self._collate = value
            self._character_set = self.collation[value]

    @property
    def character_set(self):
        """Get the appropriate character set value"""
        if not self._character_set:
            return self.__charset__
        else:
            return self._character_set

    @character_set.setter
    def character_set(self, value):
        """Validate the character set and set it"""
        if not value:
            pass
        elif not value in self.charset:
            raise ValueError("'%s' not a valid character set" % value)
        else:
            self._character_set = value


class MySQLUser(Base):
    """Represents a MySQL User and its associated properties"""

    not_supported_chars = re.compile("^\s|\s$|'|\"|;|`|,|/|\\\\")
    _ignore_users = CONF.ignore_users

    def __init__(self):
        self._name = None
        self._host = None
        self._password = None
        self._databases = []

    def _is_valid(self, value):
        if (not value or
                self.not_supported_chars.search(value) or
                string.find("%r" % value, "\\") != -1):
            return False
        else:
            return True

    def _is_valid_user_name(self, value):
        if (self._is_valid(value) and
                value.lower() not in self._ignore_users):
            return True
        return False

    def _is_valid_host_name(self, value):
        if value in [None, "%"]:
            # % is MySQL shorthand for "everywhere". Always permitted.
            # Null host defaults to % anyway.
            return True
        if CONF.hostname_require_ipv4:
            # Do a little legwork to determine that an address looks legit.

            if value.count('/') > 1:
                # No subnets.
                return False
            octets = value.split('.')
            if len(octets) not in range(1, 5):
                # A, A.B, A.B.C, and A.B.C.D are all valid technically.
                return False
            try:
                octets = [int(octet, 10) for octet in octets]
            except ValueError:
                # If these weren't decimal, there's a problem.
                return False
            return all([(octet >= 0) and (octet <= 255) for octet in octets])

        else:
            # If it wasn't required, anything else goes.
            return True

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not self._is_valid_user_name(value):
            raise ValueError("'%s' is not a valid user name." % value)
        elif len(value) > 16:
            raise ValueError("User name '%s' is too long. Max length = 16." %
                             value)
        else:
            self._name = value

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, value):
        if not self._is_valid(value):
            raise ValueError("'%s' is not a valid password." % value)
        else:
            self._password = value

    @property
    def databases(self):
        return self._databases

    @databases.setter
    def databases(self, value):
        mydb = MySQLDatabase()
        mydb.name = value
        self._databases.append(mydb.serialize())

    @property
    def host(self):
        if self._host is None:
            return '%'
        return self._host

    @host.setter
    def host(self, value):
        if not self._is_valid_host_name(value):
            raise ValueError("'%s' is not a valid hostname." % value)
        else:
            self._host = value


class RootUser(MySQLUser):
    """Overrides _ignore_users from the MySQLUser class."""

    _ignore_users = []
