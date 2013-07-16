#    Copyright 2012 OpenStack Foundation
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

_ENV = None

import jinja2


def get_env():
    global _ENV
    if not _ENV:
        _ENV = create_env()
    return _ENV


def create_env():
    loader = jinja2.ChoiceLoader([
        jinja2.FileSystemLoader("/etc/trove/templates"),
        jinja2.PackageLoader("trove", "templates")
    ])
    return jinja2.Environment(loader=loader)


class SingleInstanceConfigTemplate(object):
    _location_types = {'mysql': '/etc/mysql/my.cnf',
                       'percona': '/etc/mysql/my.cnf'}

    def __init__(self, location_type, flavor_dict):
        self.config_location = self._location_types[location_type]
        self.flavor_dict = flavor_dict
        self.template = get_env().get_template("mysql.config.template")

    def render(self):
        self.config_contents = self.template.render(
            flavor=self.flavor_dict)
