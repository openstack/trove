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

import json
from datetime import datetime

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.common.exception import ModelNotFoundError
from trove.datastore import models as dstore_models
from trove.db import get_db_api
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

    def __init__(self, context, configuration_id):
        self.context = context
        self.configuration_id = configuration_id

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
            config_item = DBConfigurationParameter.create(
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
        items = DBConfigurationParameter.find_all(configuration_id=id,
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
                return DBConfiguration.find_by(id=id, deleted=False)
            else:
                return DBConfiguration.find_by(id=id,
                                               tenant_id=context.tenant,
                                               deleted=False)
        except ModelNotFoundError:
            msg = _("Configuration group with ID %s could not be found.") % id
            raise ModelNotFoundError(msg)

    @staticmethod
    def find_parameter_details(name, detail_list):
        for item in detail_list:
            if item.name == name:
                return item
        return None

    @staticmethod
    def load_items(context, id):
        datastore_v = Configuration.load_configuration_datastore_version(
            context,
            id)
        config_items = DBConfigurationParameter.find_all(
            configuration_id=id, deleted=False).all()

        detail_list = DatastoreConfigurationParameters.load_parameters(
            datastore_v.id)

        for item in config_items:
            rule = Configuration.find_parameter_details(
                str(item.configuration_key), detail_list)
            if not rule:
                continue
            if rule.data_type == 'boolean':
                item.configuration_value = bool(int(item.configuration_value))
            elif rule.data_type == 'integer':
                item.configuration_value = int(item.configuration_value)
            else:
                item.configuration_value = str(item.configuration_value)
        return config_items

    def get_configuration_overrides(self):
        """Gets the overrides dictionary to apply to an instance."""
        overrides = {}
        if self.configuration_id:
            config_items = Configuration.load_items(self.context,
                                                    id=self.configuration_id)

            for i in config_items:
                overrides[i.configuration_key] = i.configuration_value
        return overrides

    def does_configuration_need_restart(self):
        datastore_v = Configuration.load_configuration_datastore_version(
            self.context,
            self.configuration_id)
        config_items = Configuration.load_items(self.context,
                                                id=self.configuration_id)
        LOG.debug("config_items: %s" % config_items)
        detail_list = DatastoreConfigurationParameters.load_parameters(
            datastore_v.id, show_deleted=True)

        for i in config_items:
            LOG.debug("config item: %s" % i)
            details = Configuration.find_parameter_details(
                i.configuration_key, detail_list)
            LOG.debug("parameter details: %s" % details)
            if not details:
                raise exception.NotFound(uuid=i.configuration_key)
            if bool(details.restart_required):
                return True
        return False

    @staticmethod
    def save(context, configuration, configuration_items, instances):
        DBConfiguration.save(configuration)
        for item in configuration_items:
            item["deleted_at"] = None
            DBConfigurationParameter.save(item)

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


class DBConfigurationParameter(dbmodels.DatabaseModelBase):
    _data_fields = ['configuration_id', 'configuration_key',
                    'configuration_value', 'deleted',
                    'deleted_at']

    def __hash__(self):
        return self.configuration_key.__hash__()


class DBDatastoreConfigurationParameters(dbmodels.DatabaseModelBase):
    """Model for storing the configuration parameters on a datastore."""
    _auto_generated_attrs = ['id']
    _data_fields = [
        'name',
        'datastore_version_id',
        'restart_required',
        'max_size',
        'min_size',
        'data_type',
        'deleted',
        'deleted_at',
    ]
    _table_name = "datastore_configuration_parameters"
    preserve_on_delete = True


class DatastoreConfigurationParameters(object):
    def __init__(self, db_info):
        self.db_info = db_info

    @staticmethod
    def create(**kwargs):
        """Create a configuration parameter for a datastore version."""

        # Do we already have a parameter in the db?
        # yes: and its deleted then modify the param
        # yes: and its not deleted then error on create.
        # no: then just create the new param
        ds_v_id = kwargs.get('datastore_version_id')
        config_param_name = kwargs.get('name')
        try:
            param = DatastoreConfigurationParameters.load_parameter_by_name(
                ds_v_id,
                config_param_name,
                show_deleted=True)
            if param.deleted == 1:
                param.restart_required = kwargs.get('restart_required')
                param.data_type = kwargs.get('data_type')
                param.max_size = kwargs.get('max_size')
                param.min_size = kwargs.get('min_size')
                param.deleted = 0
                param.save()
                return param
            else:
                raise exception.ConfigurationParameterAlreadyExists(
                    parameter_name=config_param_name,
                    datastore_version=ds_v_id)
        except exception.NotFound:
            pass
        config_param = DBDatastoreConfigurationParameters.create(
            **kwargs)
        return config_param

    @staticmethod
    def delete(version_id, config_param_name):
        config_param = DatastoreConfigurationParameters.load_parameter_by_name(
            version_id, config_param_name)
        config_param.deleted = True
        config_param.deleted_at = datetime.utcnow()
        config_param.save()

    @classmethod
    def load_parameters(cls, datastore_version_id, show_deleted=False):
        try:
            if show_deleted:
                return DBDatastoreConfigurationParameters.find_all(
                    datastore_version_id=datastore_version_id
                )
            else:
                return DBDatastoreConfigurationParameters.find_all(
                    datastore_version_id=datastore_version_id,
                    deleted=False
                )
        except exception.NotFound:
            raise exception.NotFound(uuid=datastore_version_id)

    @classmethod
    def load_parameter(cls, config_id, show_deleted=False):
        try:
            if show_deleted:
                return DBDatastoreConfigurationParameters.find_by(
                    id=config_id
                )
            else:
                return DBDatastoreConfigurationParameters.find_by(
                    id=config_id, deleted=False
                )
        except exception.NotFound:
            raise exception.NotFound(uuid=config_id)

    @classmethod
    def load_parameter_by_name(cls, datastore_version_id, config_param_name,
                               show_deleted=False):
        try:
            if show_deleted:
                return DBDatastoreConfigurationParameters.find_by(
                    datastore_version_id=datastore_version_id,
                    name=config_param_name
                )
            else:
                return DBDatastoreConfigurationParameters.find_by(
                    datastore_version_id=datastore_version_id,
                    name=config_param_name,
                    deleted=False
                )
        except exception.NotFound:
            raise exception.NotFound(uuid=config_param_name)


def create_or_update_datastore_configuration_parameter(name,
                                                       datastore_version_id,
                                                       restart_required,
                                                       data_type,
                                                       max_size,
                                                       min_size):
    get_db_api().configure_db(CONF)
    datastore_version = dstore_models.DatastoreVersion.load_by_uuid(
        datastore_version_id)
    try:
        config = DatastoreConfigurationParameters.load_parameter_by_name(
            datastore_version_id, name, show_deleted=True)
        config.restart_required = restart_required
        config.max_size = max_size
        config.min_size = min_size
        config.data_type = data_type
        get_db_api().save(config)
    except exception.NotFound:
        config = DBDatastoreConfigurationParameters(
            id=utils.generate_uuid(),
            name=name,
            datastore_version_id=datastore_version.id,
            restart_required=restart_required,
            data_type=data_type,
            max_size=max_size,
            min_size=min_size,
            deleted=False,
        )
        get_db_api().save(config)


def load_datastore_configuration_parameters(datastore,
                                            datastore_version,
                                            config_file):
    get_db_api().configure_db(CONF)
    (ds, ds_v) = dstore_models.get_datastore_version(
        type=datastore, version=datastore_version)
    with open(config_file) as f:
        config = json.load(f)
        for param in config['configuration-parameters']:
            create_or_update_datastore_configuration_parameter(
                param['name'],
                ds_v.id,
                param['restart_required'],
                param['type'],
                param.get('max'),
                param.get('min'),
            )


def persisted_models():
    return {
        'configurations': DBConfiguration,
        'configuration_parameters': DBConfigurationParameter,
        'datastore_configuration_parameters': DBDatastoreConfigurationParameters,  # noqa
    }
