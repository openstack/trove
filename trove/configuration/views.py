# Copyright 2014 Rackspace
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

from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class ConfigurationView(object):

    def __init__(self, configuration):
        self.configuration = configuration

    def data(self):
        configuration_dict = {
            "id": self.configuration.id,
            "name": self.configuration.name,
            "description": self.configuration.description,
            "datastore_version_id": self.configuration.datastore_version_id,
        }

        return {"configuration": configuration_dict}


class ConfigurationsView(object):

    def __init__(self, configurations):
        self.configurations = configurations

    def data(self):
        data = []

        for configuration in self.configurations:
            data.append(self.data_for_configuration(configuration))

        return {"configurations": data}

    def data_for_configuration(self, configuration):
        view = ConfigurationView(configuration)
        return view.data()['configuration']


class DetailedConfigurationInstancesView(object):

    def __init__(self, instances):
        self.instances = instances

    def instance_data(self):
        instances_list = []
        if self.instances:
            for instance in self.instances:
                instances_list.append(
                    {
                        "id": instance.id,
                        "name": instance.name
                    }
                )
        return instances_list

    def data(self):

        return {"instances": self.instance_data()}


class DetailedConfigurationView(object):

    def __init__(self, configuration, configuration_items):
        self.configuration = configuration
        self.configuration_items = configuration_items

    def data(self):
        values = {}

        for configItem in self.configuration_items:
            key = configItem.configuration_key
            value = configItem.configuration_value
            values[key] = value
        configuration_dict = {
            "id": self.configuration.id,
            "name": self.configuration.name,
            "description": self.configuration.description,
            "values": values,
            "datastore_version_id": self.configuration.datastore_version_id,
        }

        return {"configuration": configuration_dict}


class ConfigurationParametersView(object):

    def __init__(self, configuration_parameters):
        self.configuration_parameters = configuration_parameters

    def data(self):
        return self.configuration_parameters
