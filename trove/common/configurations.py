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
import json
from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.openstack.common import log as logging
from six.moves import configparser


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
ENV = utils.ENV


def _get_item(key, dictList):
    for item in dictList:
        if key == item.get('name'):
            return item


def do_configs_require_restart(overrides, datastore_manager='mysql'):
    rules = get_validation_rules(datastore_manager=datastore_manager)
    LOG.debug("overrides: %s" % overrides)
    LOG.debug("rules?: %s" % rules)
    for key in overrides.keys():
        rule = _get_item(key, rules['configuration-parameters'])
        LOG.debug("checking the rule: %s" % rule)
        if rule.get('restart_required'):
            return True
    return False


def get_validation_rules(datastore_manager='mysql'):
    try:
        config_location = ("%s/validation-rules.json" % datastore_manager)
        template = ENV.get_template(config_location)
        return json.loads(template.render())
    except Exception:
        msg = "This operation is not supported for this datastore at this time"
        LOG.exception(msg)
        raise exception.UnprocessableEntity(message=msg)


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
            # python 2.6 configparser doesnt like params without values
            elif line_clean.startswith('[') and line_clean.endswith(']'):
                ret.append(line_clean)
            elif line_clean and "=" not in line_clean:
                LOG.debug("fixing line without '=' in it: %s" % line_clean)
                ret.append(line_clean + " = 1")
            else:
                ret.append(line_clean)
        rendered = "\n".join(ret)
        return rendered
