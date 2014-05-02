#    Copyright 2012 OpenStack Foundation
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

import jinja2
from trove.common import cfg
from trove.common import configurations
from trove.common import exception
from trove.common import utils
from trove.openstack.common import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

ENV = utils.ENV

# TODO(cp16net) Maybe this should be moved to a config dict
SERVICE_PARSERS = {
    'mysql': configurations.MySQLConfParser,
    'percona': configurations.MySQLConfParser,
}


class SingleInstanceConfigTemplate(object):
    """This class selects a single configuration file by database type for
        rendering on the guest
    """

    template_name = "config.template"

    def __init__(self, datastore_version, flavor_dict, instance_id):
        """Constructor

        :param datastore_version: The datastore version.
        :type datastore_version: DatastoreVersion
        :param flavor_dict: dict containing flavor details for use in jinja.
        :type flavor_dict: dict.
        :param instance_id: trove instance id
        :type instance_id: str

        """
        self.flavor_dict = flavor_dict
        self.datastore_version = datastore_version
        #TODO(tim.simpson): The current definition of datastore_version is a
        #                   bit iffy and I believe will change soon, so I'm
        #                   creating a dictionary here for jinja to consume
        #                   rather than pass in the datastore version object.
        self.datastore_dict = {
            'name': self.datastore_version.datastore_name,
            'manager': self.datastore_version.manager,
            'version': self.datastore_version.name,
        }
        self.instance_id = instance_id

    def get_template(self):
        patterns = ['{name}/{version}/{template_name}',
                    '{name}/{template_name}',
                    '{manager}/{template_name}']
        context = self.datastore_dict.copy()
        context['template_name'] = self.template_name
        names = [name.format(**context) for name in patterns]
        return ENV.select_template(names)

    def render(self, **kwargs):
        """Renders the jinja template

        :returns: str -- The rendered configuration file

        """
        template = self.get_template()
        server_id = self._calculate_unique_id()
        self.config_contents = template.render(
            flavor=self.flavor_dict,
            datastore=self.datastore_dict,
            server_id=server_id, **kwargs)
        return self.config_contents

    def render_dict(self):
        """
        Renders the default configuration template file as a dictionary
        to apply the default configuration dynamically.
        """
        config = self.render()
        cfg_parser = SERVICE_PARSERS.get(self.datastore_version.manager)
        if not cfg_parser:
            raise exception.NoConfigParserFound(
                datastore_manager=self.datastore_version.manager)
        return cfg_parser(config).parse()

    def _calculate_unique_id(self):
        """
        Returns a positive unique id based off of the instance id

        :return: a positive integer
        """
        return abs(hash(self.instance_id) % (2 ** 31))


class OverrideConfigTemplate(SingleInstanceConfigTemplate):
    template_name = "override.config.template"


def load_heat_template(datastore_manager):
    template_filename = "%s/heat.template" % datastore_manager
    try:
        template_obj = ENV.get_template(template_filename)
        return template_obj
    except jinja2.TemplateNotFound:
        msg = "Missing heat template for %s" % datastore_manager
        LOG.error(msg)
        raise exception.TroveError(msg)
