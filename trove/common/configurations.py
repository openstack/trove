#    Copyright 2014 Rackspace Hosting
#    All Rights Reserved.
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

from trove.common import stream_codecs


class RedisConfParser(object):

    CODEC = stream_codecs.PropertiesCodec()

    def __init__(self, config):
        self.config = config

    def parse(self):
        return self.CODEC.deserialize(self.config).items()


class MySQLConfParser(object):

    SERVER_CONF_SECTION = 'mysqld'
    CODEC = stream_codecs.IniCodec(
        default_value='1', comment_markers=('#', ';', '!'))

    def __init__(self, config):
        self.config = config

    def parse(self):
        config_dict = self.CODEC.deserialize(self.config)
        mysqld_section_dict = config_dict[self.SERVER_CONF_SECTION]
        return mysqld_section_dict.items()


class MongoDBConfParser(object):

    CODEC = stream_codecs.SafeYamlCodec(default_flow_style=False)

    def __init__(self, config):
        self.config = config

    def parse(self):
        return self.CODEC.deserialize(self.config).items()


class PostgresqlConfParser(object):

    CODEC = stream_codecs.PropertiesCodec(delimiter='=')

    def __init__(self, config):
        self.config = config

    def parse(self):
        return self.CODEC.deserialize(self.config).items()
