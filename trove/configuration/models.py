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

from datetime import datetime

from trove.common import cfg
from trove.common import configurations
from trove.common.exception import ModelNotFoundError
from trove.datastore import models as dstore_models
from trove.db import models as dbmodels
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.taskmanager import api as task_api


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Configurations(object):

    DEFAULT_LIMIT = CONF.configurations_page_size

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        if context.is_admin:
            db_info = DBConfiguration.find_all(deleted=False)
            if db_info.count() == 0:
                LOG.debug("No configurations found for admin user")
        else:
            db_info = DBConfiguration.find_all(tenant_id=context.tenant,
                                               deleted=False)
            if db_info.count() == 0:
                LOG.debug("No configurations found for tenant %s"
                          % context.tenant)

        limit = int(context.limit or Configurations.DEFAULT_LIMIT)
        if limit > Configurations.DEFAULT_LIMIT:
            limit = Configurations.DEFAULT_LIMIT

        data_view = DBConfiguration.find_by_pagination('configurations',
                                                       db_info,
                                                       "foo",
                                                       limit=limit,
                                                       marker=context.marker)
        next_marker = data_view.next_page_marker
        return data_view.collection, next_marker


class Configuration(object):

    @property
    def instances(self):
        return self.instances

    @property
    def items(self):
        return self.items

    @staticmethod
    def create(name, description, tenant_id, datastore, datastore_version):
        configurationGroup = DBConfiguration.create(
            name=name,
            description=description,
            tenant_id=tenant_id,
            datastore_version_id=datastore_version)
        return configurationGroup

    @staticmethod
    def create_items(cfg_id, values):
        LOG.debug("Saving configuration values for %s - "
                  "values: %s" % (cfg_id, values))
        config_items = []
        for key, val in values.iteritems():
            config_item = ConfigurationParameter.create(
                configuration_id=cfg_id,
                configuration_key=key,
                configuration_value=val)
            config_items.append(config_item)
        return config_items

    @staticmethod
    def delete(context, group):
        deleted_at = datetime.utcnow()
        Configuration.remove_all_items(context, group.id, deleted_at)
        group.deleted = True
        group.deleted_at = deleted_at
        group.save()

    @staticmethod
    def remove_all_items(context, id, deleted_at):
        items = ConfigurationParameter.find_all(configuration_id=id,
                                                deleted=False).all()
        LOG.debug("Removing all configuration values for %s" % id)
        for item in items:
            item.deleted = True
            item.deleted_at = deleted_at
            item.save()

    @staticmethod
    def load_configuration_datastore_version(context, id):
        config = Configuration.load(context, id)
        datastore_version = dstore_models.DatastoreVersion.load_by_uuid(
            config.datastore_version_id)
        return datastore_version

    @staticmethod
    def load(context, id):
        try:
            if context.is_admin:
                config_info = DBConfiguration.find_by(id=id,
                                                      deleted=False)
            else:
                config_info = DBConfiguration.find_by(id=id,
                                                      tenant_id=context.tenant,
                                                      deleted=False)
        except ModelNotFoundError:
            msg = _("Configuration group with ID %s could not be found.") % id
            raise ModelNotFoundError(msg)
        return config_info

    @staticmethod
    def load_items(context, id):
        datastore = Configuration.load_configuration_datastore_version(context,
                                                                       id)
        config_items = ConfigurationParameter.find_all(configuration_id=id,
                                                       deleted=False).all()
        rules = configurations.get_validation_rules(
            datastore_manager=datastore.manager)

        def _get_rule(key):
            for rule in rules['configuration-parameters']:
                if str(rule.get('name')) == key:
                    return rule

        for item in config_items:
            rule = _get_rule(str(item.configuration_key))
            if rule.get('type') == 'boolean':
                item.configuration_value = bool(int(item.configuration_value))
            elif rule.get('type') == 'integer':
                item.configuration_value = int(item.configuration_value)
            else:
                item.configuration_value = str(item.configuration_value)
        return config_items

    @staticmethod
    def get_configuration_overrides(context, configuration_id):
        """Gets the overrides dictionary to apply to an instance."""
        overrides = {}
        if configuration_id:
            config_items = Configuration.load_items(context,
                                                    id=configuration_id)

            for i in config_items:
                overrides[i.configuration_key] = i.configuration_value
        return overrides

    @staticmethod
    def save(context, configuration, configuration_items, instances):
        DBConfiguration.save(configuration)
        for item in configuration_items:
            item["deleted_at"] = None
            ConfigurationParameter.save(item)

        items = Configuration.load_items(context, configuration.id)

        for instance in instances:
            LOG.debug("Configuration %s being applied to "
                      "instance: %s" % (configuration.id, instance.id))
            overrides = {}
            for i in items:
                overrides[i.configuration_key] = i.configuration_value

            task_api.API(context).update_overrides(instance.id, overrides)


class DBConfiguration(dbmodels.DatabaseModelBase):
    _data_fields = ['name', 'description', 'tenant_id', 'datastore_version_id',
                    'deleted', 'deleted_at', 'created', 'updated']

    @property
    def datastore(self):
        datastore_version = dstore_models.DatastoreVersion.load_by_uuid(
            self.datastore_version_id)
        datastore = dstore_models.Datastore.load(
            datastore_version.datastore_id)
        return datastore

    @property
    def datastore_version(self):
        datastore_version = dstore_models.DatastoreVersion.load_by_uuid(
            self.datastore_version_id)
        return datastore_version


class ConfigurationParameter(dbmodels.DatabaseModelBase):
    _data_fields = ['configuration_id', 'configuration_key',
                    'configuration_value', 'deleted',
                    'deleted_at']

    def __hash__(self):
        return self.configuration_key.__hash__()


def persisted_models():
    return {
        'configurations': DBConfiguration,
        'configuration_parameters': ConfigurationParameter
    }
