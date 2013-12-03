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

import jinja2
from trove.common import cfg
from trove.common import exception
from trove.openstack.common import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

ENV = jinja2.Environment(loader=jinja2.ChoiceLoader([
    jinja2.FileSystemLoader(CONF.template_path),
    jinja2.PackageLoader("trove", "templates"),
]))


class SingleInstanceConfigTemplate(object):
    """This class selects a single configuration file by database type for
    rendering on the guest """

    def __init__(self, datastore_manager, flavor_dict, instance_id):
        """Constructor

        :param datastore_manager: The datastore manager.
        :type name: str.
        :param flavor_dict: dict containing flavor details for use in jinja.
        :type flavor_dict: dict.
        :param instance_id: trove instance id
        :type: instance_id: str

        """
        self.flavor_dict = flavor_dict
        template_filename = "%s/config.template" % datastore_manager
        self.template = ENV.get_template(template_filename)
        self.instance_id = instance_id

    def render(self):
        """Renders the jinja template

        :returns: str -- The rendered configuration file

        """
        server_id = self._calculate_unique_id()
        self.config_contents = self.template.render(
            flavor=self.flavor_dict, server_id=server_id)
        return self.config_contents

    def _calculate_unique_id(self):
        """
        Returns a positive unique id based off of the instance id

        :return: a positive integer
        """
        return abs(hash(self.instance_id) % (2 ** 31))


def load_heat_template(datastore_manager):
    template_filename = "%s/heat.template" % datastore_manager
    try:
        template_obj = ENV.get_template(template_filename)
        return template_obj
    except jinja2.TemplateNotFound:
        msg = "Missing heat template for %s" % datastore_manager
        LOG.error(msg)
        raise exception.TroveError(msg)
