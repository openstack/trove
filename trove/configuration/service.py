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

from oslo_log import log as logging

from trove.cluster import models as cluster_models
import trove.common.apischema as apischema
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import notification
from trove.common.notification import StartNotification, EndNotification
from trove.common import pagination
from trove.common import policy
from trove.common import timeutils
from trove.common import wsgi
from trove.configuration import models
from trove.configuration.models import DBConfigurationParameter
from trove.configuration import views
from trove.datastore import models as ds_models
from trove.instance import models as instances_models


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ConfigurationsController(wsgi.Controller):

    schemas = apischema.configuration

    @classmethod
    def authorize_config_action(cls, context, config_rule_name, config):
        policy.authorize_on_target(
            context, 'configuration:%s' % config_rule_name,
            {'tenant': config.tenant_id})

    def index(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configs, marker = models.Configurations.load(context)
        policy.authorize_on_tenant(context, 'configuration:index')
        view = views.ConfigurationsView(configs)
        paged = pagination.SimplePaginatedDataView(req.url, 'configurations',
                                                   view, marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        LOG.debug("Showing configuration group %(id)s on tenant %(tenant)s",
                  {"tenant": tenant_id, "id": id})
        context = req.environ[wsgi.CONTEXT_KEY]
        configuration = models.Configuration.load(context, id)
        self.authorize_config_action(context, 'show', configuration)
        configuration_items = models.Configuration.load_items(context, id)

        find_instance = {
            'configuration_id': configuration.id,
            'deleted': False
        }
        if not context.is_admin:
            find_instance['tenant_id'] = context.project_id

        configuration.instance_count = instances_models.DBInstance.find_all(
            **find_instance).count()

        return wsgi.Result(views.DetailedConfigurationView(
                           configuration,
                           configuration_items).data(), 200)

    def instances(self, req, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        configuration = models.Configuration.load(context, id)
        self.authorize_config_action(context, 'instances', configuration)

        kwargs = {
            'configuration_id': configuration.id,
            'deleted': False
        }
        if not context.is_admin:
            kwargs['tenant_id'] = context.project_id
        instances = instances_models.DBInstance.find_all(**kwargs)

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
        LOG.debug("req : '%s'\n\n", req)
        LOG.debug("body : '%s'\n\n", req)

        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'configuration:create')
        context.notification = notification.DBaaSConfigurationCreate(
            context, request=req)
        name = body['configuration']['name']
        description = body['configuration'].get('description')
        values = body['configuration']['values']

        msg = ("Creating configuration group on tenant "
               "%(tenant_id)s with name: %(cfg_name)s")
        LOG.info(msg, {"tenant_id": tenant_id, "cfg_name": name})

        datastore_args = body['configuration'].get('datastore', {})
        datastore, datastore_version = (
            ds_models.get_datastore_version(**datastore_args))

        with StartNotification(context, name=name, datastore=datastore.name,
                               datastore_version=datastore_version.name):
            configItems = []
            if values:
                # validate that the values passed in are permitted by the
                # operator.
                ConfigurationsController._validate_configuration(
                    body['configuration']['values'],
                    datastore_version,
                    models.DatastoreConfigurationParameters.load_parameters(
                        datastore_version.id))

                for k, v in values.items():
                    configItems.append(DBConfigurationParameter(
                        configuration_key=k,
                        configuration_value=v))

            cfg_group = models.Configuration.create(name, description,
                                                    tenant_id, datastore.id,
                                                    datastore_version.id)
            with EndNotification(context, configuration_id=cfg_group.id):
                cfg_group_items = models.Configuration.create_items(
                    cfg_group.id, values)

        view_data = views.DetailedConfigurationView(cfg_group,
                                                    cfg_group_items)
        return wsgi.Result(view_data.data(), 200)

    def delete(self, req, tenant_id, id):
        msg = ("Deleting configuration group %(cfg_id)s on tenant: "
               "%(tenant_id)s")
        LOG.info(msg, {"tenant_id": tenant_id, "cfg_id": id})

        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        self.authorize_config_action(context, 'delete', group)
        context.notification = notification.DBaaSConfigurationDelete(
            context, request=req)
        with StartNotification(context, configuration_id=id):
            instances = instances_models.DBInstance.find_all(
                tenant_id=context.project_id,
                configuration_id=id,
                deleted=False).all()
            if instances:
                raise exception.InstanceAssignedToConfiguration()
            models.Configuration.delete(context, group)
        return wsgi.Result(None, 202)

    def update(self, req, body, tenant_id, id):
        msg = ("Updating configuration group %(cfg_id)s for tenant "
               "id %(tenant_id)s")
        LOG.info(msg, {"tenant_id": tenant_id, "cfg_id": id})

        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        # Note that changing the configuration group will also
        # indirectly affect all the instances which attach it.
        #
        # The Trove instance itself won't be changed (the same group is still
        # attached) but the configuration values will.
        #
        # The operator needs to keep this in mind when defining the related
        # policies.
        self.authorize_config_action(context, 'update', group)

        # if name/description are provided in the request body, update the
        # model with these values as well.
        if 'name' in body['configuration']:
            group.name = body['configuration']['name']

        if 'description' in body['configuration']:
            group.description = body['configuration']['description']

        context.notification = notification.DBaaSConfigurationUpdate(
            context, request=req)
        with StartNotification(context, configuration_id=id,
                               name=group.name, description=group.description):
            items = self._configuration_items_list(group,
                                                   body['configuration'])
            deleted_at = timeutils.utcnow()
            models.Configuration.remove_all_items(context, group.id,
                                                  deleted_at)
            models.Configuration.save(group, items)
            self._refresh_on_all_instances(context, id)
            self._refresh_on_all_clusters(context, id)

        return wsgi.Result(None, 202)

    def edit(self, req, body, tenant_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        group = models.Configuration.load(context, id)
        self.authorize_config_action(context, 'edit', group)
        context.notification = notification.DBaaSConfigurationEdit(
            context, request=req)
        with StartNotification(context, configuration_id=id):
            items = self._configuration_items_list(group,
                                                   body['configuration'])
            models.Configuration.save(group, items)
            self._refresh_on_all_instances(context, id)
            self._refresh_on_all_clusters(context, id)

    def _refresh_on_all_instances(self, context, configuration_id):
        """Refresh a configuration group on all single instances.
        """
        single_instances = instances_models.DBInstance.find_all(
            tenant_id=context.project_id,
            configuration_id=configuration_id,
            cluster_id=None,
            deleted=False).all()

        config = models.Configuration(context, configuration_id)
        for dbinstance in single_instances:
            LOG.info("Re-applying configuration %s to instance: %s",
                     configuration_id, dbinstance.id)
            instance = instances_models.Instance.load(context, dbinstance.id)
            instance.update_configuration(config)

    def _refresh_on_all_clusters(self, context, configuration_id):
        """Refresh a configuration group on all clusters.
        """
        LOG.debug("Re-applying configuration group '%s' to all clusters.",
                  configuration_id)
        clusters = cluster_models.DBCluster.find_all(
            tenant_id=context.project_id,
            configuration_id=configuration_id,
            deleted=False).all()

        for dbcluster in clusters:
            LOG.debug("Re-applying configuration to cluster: %s", dbcluster.id)
            cluster = cluster_models.Cluster.load(context, dbcluster.id)
            cluster.configuration_attach(configuration_id)

    def _configuration_items_list(self, group, configuration):
        ds_version_id = group.datastore_version_id
        ds_version = ds_models.DatastoreVersion.load_by_uuid(ds_version_id)
        items = []
        if 'values' in configuration:
            # validate that the values passed in are permitted by the operator.
            ConfigurationsController._validate_configuration(
                configuration['values'],
                ds_version,
                models.DatastoreConfigurationParameters.load_parameters(
                    ds_version.id))
            for k, v in configuration['values'].items():
                items.append(DBConfigurationParameter(
                    configuration_id=group.id,
                    configuration_key=k,
                    configuration_value=v,
                    deleted=False))
        return items

    @staticmethod
    def _validate_configuration(values, datastore_version, config_rules):
        LOG.info("Validating configuration values")

        # create rules dictionary based on parameter name
        rules_lookup = {}
        for item in config_rules:
            rules_lookup[item.name.lower()] = item

        # checking if there are any rules for the datastore
        if not rules_lookup:
            output = {"version": datastore_version.name,
                      "name": datastore_version.datastore_name}
            msg = _("Configuration groups are not supported for this "
                    "datastore: %(name)s %(version)s") % output
            raise exception.UnprocessableEntity(message=msg)

        for k, v in values.items():
            key = k.lower()
            # parameter name validation
            if key not in rules_lookup:
                output = {"key": k,
                          "version": datastore_version.name,
                          "name": datastore_version.datastore_name}
                msg = _("The configuration parameter %(key)s is not "
                        "supported for this datastore: "
                        "%(name)s %(version)s.") % output
                raise exception.UnprocessableEntity(message=msg)

            rule = rules_lookup[key]

            # type checking
            value_type = rule.data_type

            if not isinstance(v, ConfigurationsController._find_type(
                    value_type)):
                output = {"key": k, "type": value_type}
                msg = _("The value provided for the configuration "
                        "parameter %(key)s is not of type %(type)s.") % output
                raise exception.UnprocessableEntity(message=msg)

            # integer min/max checking
            if isinstance(v, int) and not isinstance(v, bool):
                if rule.min_size is not None:
                    try:
                        min_value = int(rule.min_size)
                    except ValueError:
                        raise exception.TroveError(_(
                            "Invalid or unsupported min value defined in the "
                            "configuration-parameters configuration file. "
                            "Expected integer."))
                    if v < min_value:
                        output = {"key": k, "min": min_value}
                        message = _(
                            "The value for the configuration parameter "
                            "%(key)s is less than the minimum allowed: "
                            "%(min)s") % output
                        raise exception.UnprocessableEntity(message=message)

                if rule.max_size is not None:
                    try:
                        max_value = int(rule.max_size)
                    except ValueError:
                        raise exception.TroveError(_(
                            "Invalid or unsupported max value defined in the "
                            "configuration-parameters configuration file. "
                            "Expected integer."))
                    if v > max_value:
                        output = {"key": k, "max": max_value}
                        message = _(
                            "The value for the configuration parameter "
                            "%(key)s is greater than the maximum "
                            "allowed: %(max)s") % output
                        raise exception.UnprocessableEntity(message=message)

    @staticmethod
    def _find_type(value_type):
        if value_type == "boolean":
            return bool
        elif value_type == "string":
            return str
        elif value_type == "integer":
            return int
        elif value_type == "float":
            return float
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

    @classmethod
    def authorize_request(cls, req, rule_name):
        """Parameters (configuration templates) bind to a datastore.
        Datastores are not owned by any particular tenant so we only check
        the current tenant is allowed to perform the action.
        """
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'configuration-parameter:%s'
                                   % rule_name)

    def index(self, req, tenant_id, datastore, id):
        self.authorize_request(req, 'index')
        ds, ds_version = ds_models.get_datastore_version(
            type=datastore, version=id)
        rules = models.DatastoreConfigurationParameters.load_parameters(
            ds_version.id)
        return wsgi.Result(views.ConfigurationParametersView(rules).data(),
                           200)

    def show(self, req, tenant_id, datastore, id, name):
        self.authorize_request(req, 'show')
        ds, ds_version = ds_models.get_datastore_version(
            type=datastore, version=id)
        rule = models.DatastoreConfigurationParameters.load_parameter_by_name(
            ds_version.id, name)
        return wsgi.Result(views.ConfigurationParameterView(rule).data(), 200)

    def index_by_version(self, req, tenant_id, version):
        self.authorize_request(req, 'index_by_version')
        ds_version = ds_models.DatastoreVersion.load_by_uuid(version)
        rules = models.DatastoreConfigurationParameters.load_parameters(
            ds_version.id)
        return wsgi.Result(views.ConfigurationParametersView(rules).data(),
                           200)

    def show_by_version(self, req, tenant_id, version, name):
        self.authorize_request(req, 'show_by_version')
        ds_models.DatastoreVersion.load_by_uuid(version)
        rule = models.DatastoreConfigurationParameters.load_parameter_by_name(
            version, name)
        return wsgi.Result(views.ConfigurationParameterView(rule).data(), 200)
