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

from oslo_utils import strutils


class ConfigurationView(object):

    def __init__(self, configuration):
        self.configuration = configuration

    def data(self):
        configuration_dict = {
            "id": self.configuration.id,
            "name": self.configuration.name,
            "description": self.configuration.description,
            "created": self.configuration.created,
            "updated": self.configuration.updated,
            "datastore_version_id":
            self.configuration.datastore_version_id,
            "datastore_name":
            self.configuration.datastore.name,
            "datastore_version_name":
            self.configuration.datastore_version.name}

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
            "values": strutils.mask_dict_password(values),
            "created": self.configuration.created,
            "updated": self.configuration.updated,
            "instance_count":
                getattr(self.configuration, "instance_count", 0),
            "datastore_name": self.configuration.datastore.name,
            "datastore_version_id":
                self.configuration.datastore_version_id,
            "datastore_version_name":
                self.configuration.datastore_version.name,
            "datastore_version_number":
                self.configuration.datastore_version.version
        }

        return {"configuration": configuration_dict}


class ConfigurationParameterView(object):

    def __init__(self, config):
        self.config = config

    def data(self):
        # v1 api is to be a 'true' or 'false' json boolean instead of 1/0
        restart_required = True if self.config.restart_required else False
        ret = {
            "name": self.config.name,
            "datastore_version_id": self.config.datastore_version_id,
            "restart_required": restart_required,
            "type": self.config.data_type,
        }
        if self.config.max_size:
            ret["max"] = int(self.config.max_size)
        if self.config.min_size:
            ret["min"] = int(self.config.min_size)
        return ret


class ConfigurationParametersView(object):

    def __init__(self, configs):
        self.configs = configs

    def data(self):
        params = []
        for p in self.configs:
            param = ConfigurationParameterView(p)
            params.append(param.data())
        return {"configuration-parameters": params}
