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


from trove.common import exception
from trove.common import wsgi
from trove.common.auth import admin_context
from trove.configuration import models as config_models
from trove.datastore import models as ds_models
from trove.extensions.mgmt.configuration import views
from trove.openstack.common import log as logging
from trove.common.i18n import _
import trove.common.apischema as apischema


LOG = logging.getLogger(__name__)


class ConfigurationsParameterController(wsgi.Controller):
    """Controller for configuration parameters functionality."""
    schemas = apischema.mgmt_configuration

    @admin_context
    def index(self, req, tenant_id, version_id):
        """List all configuration parameters."""
        ds_version = ds_models.DatastoreVersion.load_by_uuid(version_id)
        config_params = config_models.DatastoreConfigurationParameters
        rules = config_params.load_parameters(
            ds_version.id, show_deleted=True)
        return wsgi.Result(views.MgmtConfigurationParametersView(rules).data(),
                           200)

    @admin_context
    def show(self, req, tenant_id, version_id, id):
        """Show a configuration parameter."""
        ds_models.DatastoreVersion.load_by_uuid(version_id)
        config_params = config_models.DatastoreConfigurationParameters
        rule = config_params.load_parameter_by_name(
            version_id, id, show_deleted=True)
        return wsgi.Result(views.MgmtConfigurationParameterView(rule).data(),
                           200)

    def _validate_data_type(self, parameter):
        min_size = None
        max_size = None
        data_type = parameter['data_type']
        if data_type == "integer":
            if 'max_size' not in parameter:
                raise exception.BadRequest(_("max_size is required for "
                                             "integer data type."))
            if 'min_size' not in parameter:
                raise exception.BadRequest(_("min_size is required for "
                                             "integer data type."))
            max_size = int(parameter['max_size'])
            min_size = int(parameter['min_size'])
            if max_size < min_size:
                raise exception.BadRequest(
                    _("max_size must be greater than or equal to min_size."))
        return data_type, min_size, max_size

    @admin_context
    def create(self, req, body, tenant_id, version_id):
        """Create configuration parameter for datastore version."""
        LOG.info(_("Creating configuration parameter for datastore"))
        LOG.debug("req : '%s'\n\n" % req)
        LOG.debug("body : '%s'\n\n" % body)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))

        parameter = body['configuration-parameter']
        name = parameter['name']
        restart_required = bool(parameter['restart_required'])
        data_type, min_size, max_size = self._validate_data_type(parameter)
        datastore_version = ds_models.DatastoreVersion.load_by_uuid(version_id)

        rule = config_models.DatastoreConfigurationParameters.create(
            name=name,
            datastore_version_id=datastore_version.id,
            restart_required=restart_required,
            data_type=data_type,
            max_size=max_size,
            min_size=min_size
        )
        return wsgi.Result(
            views.MgmtConfigurationParameterView(rule).data(),
            200)

    @admin_context
    def update(self, req, body, tenant_id, version_id, id):
        """Updating configuration parameter for datastore version."""
        LOG.info(_("Updating configuration parameter for datastore"))
        LOG.debug("req : '%s'\n\n" % req)
        LOG.debug("body : '%s'\n\n" % body)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))

        parameter = body['configuration-parameter']
        restart_required = bool(parameter['restart_required'])
        data_type, min_size, max_size = self._validate_data_type(parameter)
        ds_models.DatastoreVersion.load_by_uuid(version_id)
        ds_config_params = config_models.DatastoreConfigurationParameters
        param = ds_config_params.load_parameter_by_name(
            version_id, id)
        param.restart_required = restart_required
        param.data_type = data_type
        param.max_size = max_size
        param.min_size = min_size
        param.save()
        return wsgi.Result(
            views.MgmtConfigurationParameterView(param).data(),
            200)

    @admin_context
    def delete(self, req, tenant_id, version_id, id):
        """Delete configuration parameter for datastore version."""
        LOG.info(_("Deleting configuration parameter for datastore"))
        LOG.debug("req : '%s'\n\n" % req)
        ds_config_params = config_models.DatastoreConfigurationParameters
        try:
            ds_config_params.delete(version_id, id)
        except exception.NotFound:
            raise exception.BadRequest(_("Parameter %s does not exist in the "
                                         "database.") % id)
        return wsgi.Result(None, 204)
