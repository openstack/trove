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
from trove.common import exception
from trove.common import pagination
from trove.common import wsgi
from trove.configuration import models
from trove.configuration import views
from trove.configuration.models import ConfigurationParameter
from trove.datastore import models as ds_models
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.instance import models as instances_models
import trove.common.apischema as apischema


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ConfigurationsController(wsgi.Controller):

    schemas = apischema.configuration

    def index(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configs, marker = models.Configurations.load(context)
        view = views.ConfigurationsView(configs)
        paged = pagination.SimplePaginatedDataView(req.url, 'configurations',
                                                   view, marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configuration = models.Configuration.load(context, id)
        configuration_items = models.Configuration.load_items(context, id)

        configuration.instance_count = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=configuration.id,
            deleted=False).count()

        return wsgi.Result(views.DetailedConfigurationView(
                           configuration,
                           configuration_items).data(), 200)

    def instances(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configuration = models.Configuration.load(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=configuration.id,
            deleted=False)
        limit = int(context.limit or CONF.instances_page_size)
        if limit > CONF.instances_page_size:
            limit = CONF.instances_page_size
        data_view = instances_models.DBInstance.find_by_pagination(
            'instances', instances, "foo",
            limit=limit,
            marker=context.marker)
        view = views.DetailedConfigurationInstancesView(data_view.collection)
        paged = pagination.SimplePaginatedDataView(req.url, 'instances', view,
                                                   data_view.next_page_marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id):
        LOG.debug("req : '%s'\n\n" % req)
        LOG.debug("body : '%s'\n\n" % req)

        name = body['configuration']['name']
        description = body['configuration'].get('description')
        values = body['configuration']['values']

        datastore_args = body['configuration'].get('datastore', {})
        datastore, datastore_version = (
            ds_models.get_datastore_version(**datastore_args))

        configItems = []
        if values:
            # validate that the values passed in are permitted by the operator.
            ConfigurationsController._validate_configuration(
                body['configuration']['values'],
                datastore_manager=datastore_version.manager)

            for k, v in values.iteritems():
                configItems.append(ConfigurationParameter(
                    configuration_key=k,
                    configuration_value=v))

        cfg_group = models.Configuration.create(name, description, tenant_id,
                                                datastore.id,
                                                datastore_version.id)
        cfg_group_items = models.Configuration.create_items(cfg_group.id,
                                                            values)
        view_data = views.DetailedConfigurationView(cfg_group,
                                                    cfg_group_items)
        return wsgi.Result(view_data.data(), 200)

    def delete(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()
        if instances:
            raise exception.InstanceAssignedToConfiguration()
        models.Configuration.delete(context, group)
        return wsgi.Result(None, 202)

    def update(self, req, body, tenant_id, id):
        LOG.info(_("Updating configuration for tenant id %s") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()

        # if name/description are provided in the request body, update the
        # model with these values as well.
        if 'name' in body['configuration']:
            group.name = body['configuration']['name']

        if 'description' in body['configuration']:
            group.description = body['configuration']['description']

        items = self._configuration_items_list(group, body['configuration'])
        deleted_at = datetime.utcnow()
        models.Configuration.remove_all_items(context, group.id, deleted_at)
        LOG.info(_("loaded configuration instances: %s") % instances)
        models.Configuration.save(context, group, items, instances)
        return wsgi.Result(None, 202)

    def edit(self, req, body, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        instances = instances_models.DBInstance.find_all(
            tenant_id=context.tenant,
            configuration_id=id,
            deleted=False).all()
        LOG.info(_("loaded configuration instances: %s") % instances)
        items = self._configuration_items_list(group, body['configuration'])
        models.Configuration.save(context, group, items, instances)

    def _configuration_items_list(self, group, configuration):
        ds_version_id = group.datastore_version_id
        ds_version = ds_models.DatastoreVersion.load_by_uuid(ds_version_id)
        items = []
        LOG.info(_("loaded configuration group: %s") % group)
        if 'values' in configuration:
            # validate that the values passed in are permitted by the operator.
            ConfigurationsController._validate_configuration(
                configuration['values'], datastore_manager=ds_version.manager)
            for k, v in configuration['values'].iteritems():
                items.append(ConfigurationParameter(configuration_id=group.id,
                                                    configuration_key=k,
                                                    configuration_value=v,
                                                    deleted=False))
        return items

    @staticmethod
    def _validate_configuration(values, datastore_manager=None):
        rules = configurations.get_validation_rules(
            datastore_manager=datastore_manager)

        LOG.info(_("Validating configuration values"))
        for k, v in values.iteritems():
            # get the validation rule dictionary, which will ensure there is a
            # rule for the given key name. An exception will be thrown if no
            # valid rule is located.
            rule = ConfigurationsController._get_item(
                k, rules['configuration-parameters'])

            if rule.get('deleted_at'):
                raise exception.ConfigurationParameterDeleted(
                    parameter_name=rule.get('name'),
                    parameter_deleted_at=rule.get('deleted_at'))

            # type checking
            valueType = rule.get('type')

            if not isinstance(v, ConfigurationsController._find_type(
                    valueType)):
                output = {"key": k, "type": valueType}
                msg = _("The value provided for the configuration "
                        "parameter %(key)s is not of type %(type)s.") % output
                raise exception.UnprocessableEntity(message=msg)

            # integer min/max checking
            if isinstance(v, int) and not isinstance(v, bool):
                try:
                    min_value = int(rule.get('min'))
                except ValueError:
                    raise exception.TroveError(_(
                        "Invalid or unsupported min value defined in the "
                        "configuration-parameters configuration file. "
                        "Expected integer."))
                if v < min_value:
                    output = {"key": k, "min": min_value}
                    message = _("The value for the configuration parameter "
                                "%(key)s is less than the minimum allowed: "
                                "%(min)s") % output
                    raise exception.UnprocessableEntity(message=message)

                try:
                    max_value = int(rule.get('max'))
                except ValueError:
                    raise exception.TroveError(_(
                        "Invalid or unsupported max value defined in the "
                        "configuration-parameters configuration file. "
                        "Expected integer."))
                if v > max_value:
                    output = {"key": k, "max": max_value}
                    message = _("The value for the configuration parameter "
                                "%(key)s is greater than the maximum "
                                "allowed: %(max)s") % output
                    raise exception.UnprocessableEntity(message=message)

    @staticmethod
    def _find_type(valueType):
        if valueType == "boolean":
            return bool
        elif valueType == "string":
            return basestring
        elif valueType == "integer":
            return int
        else:
            raise exception.TroveError(_(
                "Invalid or unsupported type defined in the "
                "configuration-parameters configuration file."))

    @staticmethod
    def _get_item(key, dictList):
        for item in dictList:
            if key == item.get('name'):
                return item
        raise exception.UnprocessableEntity(
            message=_("%s is not a supported configuration parameter.") % key)


class ParametersController(wsgi.Controller):
    def index(self, req, tenant_id, datastore, id):
        ds, ds_version = ds_models.get_datastore_version(
            type=datastore, version=id)
        rules = configurations.get_validation_rules(
            datastore_manager=ds_version.manager)
        return wsgi.Result(views.ConfigurationParametersView(rules).data(),
                           200)

    def show(self, req, tenant_id, datastore, id, name):
        ds, ds_version = ds_models.get_datastore_version(
            type=datastore, version=id)
        rules = configurations.get_validation_rules(
            datastore_manager=ds_version.manager)
        for rule in rules['configuration-parameters']:
            if rule['name'] == name:
                return wsgi.Result(
                    views.ConfigurationParametersView(rule).data(), 200)
        raise exception.ConfigKeyNotFound(key=name)

    def index_by_version(self, req, tenant_id, version):
        ds_version = ds_models.DatastoreVersion.load_by_uuid(version)
        rules = configurations.get_validation_rules(
            datastore_manager=ds_version.manager)
        return wsgi.Result(views.ConfigurationParametersView(rules).data(),
                           200)

    def show_by_version(self, req, tenant_id, version, name):
        ds_version = ds_models.DatastoreVersion.load_by_uuid(version)
        rules = configurations.get_validation_rules(
            datastore_manager=ds_version.manager)
        for rule in rules['configuration-parameters']:
            if rule['name'] == name:
                return wsgi.Result(
                    views.ConfigurationParametersView(rule).data(), 200)
        raise exception.ConfigKeyNotFound(key=name)
