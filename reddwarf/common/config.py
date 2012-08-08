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

import re

from reddwarf.openstack.common import config as openstack_config


parse_options = openstack_config.parse_options
add_log_options = openstack_config.add_log_options
add_common_options = openstack_config.add_common_options
setup_logging = openstack_config.setup_logging


def _to_list(value):
    items = value.split(',')
    trimmed_list = [item.strip() for item in items]
    return trimmed_list


def get_option(options, option, **kwargs):
    if option in options and kwargs.get('type', 'str') == 'list':
        value = options[option]
        return _to_list(value)
    else:
        return openstack_config.get_option(options, option, **kwargs)


class Config(object):

    instance = {}

    @classmethod
    def load_paste_app(cls, *args, **kwargs):
        conf, app = openstack_config.load_paste_app(*args, **kwargs)
        cls.instance.update(conf)
        return conf, app

    @classmethod
    def load_paste_config(cls, *args, **kwargs):
        conf_file, conf = openstack_config.load_paste_config(*args, **kwargs)
        cls.instance.update(conf)
        return conf

    @classmethod
    def append_to_config_values(cls, *args):
        config_file = openstack_config.find_config_file(*args)
        if not config_file:
            raise RuntimeError("Unable to locate any configuration file. "
                                "Cannot load application %s" % app_name)
        # Now take the conf file values and append them to the current conf
        with open(config_file, 'r') as conf:
            for line in conf.readlines():
                    m = re.match("\s*([^#]\S+)\s*=\s*(\S+)\s*", line)
                    if m:
                        cls.instance[m.group(1)] = m.group(2)

    @classmethod
    def write_config_values(cls, *args, **kwargs):
        # Pass in empty kwargs so it doesnt mess up the config find
        config_file = openstack_config.find_config_file(*args)
        if not config_file:
            raise RuntimeError("Unable to locate any configuration file. "
                                "Cannot load application %s" % app_name)
        with open(config_file, 'a') as conf:
            for k, v in kwargs.items():
                # Start with newline to be sure its on a new line
                conf.write("\n%s=%s" % (k, v))
        # Now append them to the cls instance
        cls.append_to_config_values(*args)

    @classmethod
    def get(cls, key, default=None, **kwargs):
        # We always use a default, even if its None.
        kwargs['default'] = default
        return get_option(cls.instance, key, **kwargs)


def create_type_func(type):
    @classmethod
    def get(cls, key, default=None, **kwargs):
        kwargs['type'] = type
        return cls.get(key, default, **kwargs)
    return get


Config.get_bool = create_type_func('bool')
Config.get_float = create_type_func('float')
Config.get_int = create_type_func('int')
Config.get_list = create_type_func('list')
Config.get_str = create_type_func('str')
del create_type_func


class ConfigFacade(object):
    """This class presents an interface usable by OpenStack Common modules.

    OpenStack common uses a new config interface where the values are
    accessed as attributes directly. This presents the same interface
    so we can interface with OS common modules while we change our config
    stuff.

    """

    value_info = {}

    def __init__(self, conf):
        self.conf = conf

    def __getattr__(self, name):
        if name == "register_opts":
            def f(*args, **kwargs):
                pass
            return f
        if name in self.value_info:
            v = self.value_info[name]
            return self.conf.get(name, **v)
        return self.conf.get(name)


class OsCommonModule(object):
    """Emulates the OpenStack Common cfg module."""

    @property
    def CONF(self):
        return ConfigFacade(Config())


def create_type_func(type):
    @classmethod
    def func(cls, name, default, help):
        ConfigFacade.value_info[name] = {'default': default, 'type': type}
    return func

OsCommonModule.BoolOpt = create_type_func('bool')
OsCommonModule.IntOpt = create_type_func('int')
OsCommonModule.ListOpt = create_type_func('list')
OsCommonModule.StrOpt = create_type_func('str')
del create_type_func
