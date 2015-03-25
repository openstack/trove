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

import io
from six.moves import configparser


class MySQLConfParser(object):
    """MySQLConfParser"""
    def __init__(self, config):
        self.config = config

    def parse(self):
        good_cfg = self._remove_commented_lines(str(self.config))
        cfg_parser = configparser.ConfigParser()
        cfg_parser.readfp(io.BytesIO(str(good_cfg)))
        return cfg_parser.items("mysqld")

    def _remove_commented_lines(self, config_str):
        ret = []
        for line in config_str.splitlines():
            line_clean = line.strip()
            if line_clean.startswith('#'):
                continue
            elif line_clean.startswith('!'):
                continue
            elif line_clean.startswith(';'):
                continue
            # python 2.6 ConfigParser doesn't like params without values
            elif line_clean.startswith('[') and line_clean.endswith(']'):
                ret.append(line_clean)
            elif line_clean and "=" not in line_clean:
                ret.append(line_clean + " = 1")
            else:
                ret.append(line_clean)
        rendered = "\n".join(ret)
        return rendered
