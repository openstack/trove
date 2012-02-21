# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
"""Routines for configuring Reddwarf."""

from reddwarf.openstack.common import config as openstack_config


parse_options = openstack_config.parse_options
add_log_options = openstack_config.add_log_options
add_common_options = openstack_config.add_common_options
setup_logging = openstack_config.setup_logging
get_option = openstack_config.get_option


class Config(object):

    instance = {}

    @classmethod
    def load_paste_app(cls, *args, **kwargs):
        conf, app = openstack_config.load_paste_app(*args, **kwargs)
        cls.instance = conf
        return conf, app

    @classmethod
    def load_paste_config(cls, *args, **kwargs):
        conf_file, conf = openstack_config.load_paste_config(*args, **kwargs)
        cls.instance = conf
        return conf

    @classmethod
    def get(cls, key, default=None):
        return cls.instance.get(key, default)

    @classmethod
    def get_params_group(cls, group_key):
        group_key = group_key + "_"
        return dict((key.replace(group_key, "", 1), cls.instance.get(key))
        for key in cls.instance
        if key.startswith(group_key))


def load_app_environment(oparser):
    add_common_options(oparser)
    add_log_options(oparser)
    (options, args) = parse_options(oparser)
    conf = Config.load_paste_config('reddwarf', options, args)
    setup_logging(options=options, conf=conf)
    return conf
