# Copyright 2011 OpenStack Foundation
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

import inspect
import sys

from novaclient import api_versions
from oslo_log import log as logging

from trove.common import cfg
from trove.common import clients
from trove.common.context import TroveContext
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.configuration import models as config_models
from trove.datastore import models as datastore_models
from trove.db import get_db_api
from trove.instance.models import DBInstance


CONF = cfg.CONF


class Commands(object):

    def __init__(self):
        self.db_api = get_db_api()

    def db_sync(self, repo_path=None):
        self.db_api.db_sync(CONF, repo_path=repo_path)
        self.run_upgrade_tasks()

    def db_upgrade(self, version=None, repo_path=None):
        self.db_api.db_upgrade(CONF, version, repo_path=repo_path)
        self.run_upgrade_tasks()

    def run_upgrade_tasks(self):
        print('Running required upgrade tasks...')
        if self._check_nova_tags_exists():
            print('Nova tags already present, skipping.')
        else:
            print('Setting nova tags for existing trove nova instances.')
            self.set_nova_tags(force=True)

        # Future upgrade tasks goes here.

    def db_downgrade(self, version, repo_path=None):
        raise SystemExit(_("Database downgrade is no longer supported."))

    def execute(self):
        exec_method = getattr(self, CONF.action.name)
        args = inspect.getfullargspec(exec_method)
        args.args.remove('self')
        kwargs = {}
        for arg in args.args:
            kwargs[arg] = getattr(CONF.action, arg)
        exec_method(**kwargs)

    def datastore_update(self, datastore_name, default_version):
        try:
            datastore_models.update_datastore(datastore_name,
                                              default_version)
            print("Datastore '%s' updated." % datastore_name)
        except exception.DatastoreVersionNotFound as e:
            print(e)

    def datastore_version_update(self, datastore, version_name, manager,
                                 image_id, packages, active, registry_ext,
                                 repl_strategy,
                                 image_tags=None, version=None):
        try:
            datastore_models.update_datastore_version(
                datastore,
                version_name,
                manager,
                image_id,
                image_tags,
                packages, active,
                registry_ext, repl_strategy,
                version=version)
            print("Datastore version '%s(%s)' updated." %
                  (version_name, version or version_name))
        except exception.DatastoreNotFound as e:
            print(e)

    def db_recreate(self, repo_path):
        """Drops the database and recreates it."""
        self.db_api.drop_db()
        self.db_sync(repo_path)

    def db_load_datastore_config_parameters(self,
                                            datastore,
                                            datastore_version_name,
                                            config_file_location,
                                            version=None):
        print("Loading config parameters for datastore (%s) version (%s)"
              % (datastore, datastore_version_name))
        config_models.load_datastore_configuration_parameters(
            datastore, datastore_version_name, config_file_location,
            version_number=version)

    def db_remove_datastore_config_parameters(self, datastore,
                                              datastore_version_name,
                                              version=None):
        print("Removing config parameters for datastore (%s) version (%s)"
              % (datastore, datastore_version_name))
        config_models.remove_datastore_configuration_parameters(
            datastore, datastore_version_name, version_number=version)

    def datastore_version_flavor_add(self, datastore_name,
                                     datastore_version_name, flavor_ids,
                                     version=None):
        """Adds flavors for a given datastore version id."""
        dsmetadata = datastore_models.DatastoreVersionMetadata
        try:
            datastore_version_id = dsmetadata.datastore_version_find(
                datastore_name,
                datastore_version_name,
                version_number=version)

            dsmetadata.add_datastore_version_flavor_association(
                datastore_version_id, flavor_ids.split(","))
            print("Added flavors '%s' to the '%s' '%s'."
                  % (flavor_ids, datastore_name, datastore_version_name))
        except Exception as e:
            print(e)

    def datastore_version_flavor_delete(self, datastore_name,
                                        datastore_version_name, flavor_id,
                                        version=None):
        """Deletes a flavor's association with a given datastore."""
        try:
            dsmetadata = datastore_models.DatastoreVersionMetadata

            datastore_version_id = dsmetadata.datastore_version_find(
                datastore_name,
                datastore_version_name,
                version_number=version)

            dsmetadata.delete_datastore_version_flavor_association(
                datastore_version_id, flavor_id)
            print("Deleted flavor '%s' from '%s' '%s'."
                  % (flavor_id, datastore_name, datastore_version_name))
        except Exception as e:
            print(e)

    def datastore_version_volume_type_add(self, datastore_name,
                                          datastore_version_name,
                                          volume_type_ids, version=None):
        """Adds volume type assiciation for a given datastore version id."""
        try:
            dsmetadata = datastore_models.DatastoreVersionMetadata

            datastore_version_id = dsmetadata.datastore_version_find(
                datastore_name,
                datastore_version_name,
                version_number=version)

            dsmetadata.add_datastore_version_volume_type_association(
                datastore_version_id,
                volume_type_ids.split(","))
            print("Added volume type '%s' to the '%s' '%s'."
                  % (volume_type_ids, datastore_name, datastore_version_name))
        except Exception as e:
            print(e)

    def datastore_version_volume_type_delete(self, datastore_name,
                                             datastore_version_name,
                                             volume_type_id, version=None):
        """Deletes a volume type association with a given datastore."""
        try:
            dsmetadata = datastore_models.DatastoreVersionMetadata

            datastore_version_id = dsmetadata.datastore_version_find(
                datastore_name,
                datastore_version_name,
                version_number=version)

            dsmetadata.delete_datastore_version_volume_type_association(
                datastore_version_id, volume_type_id)
            print("Deleted volume type '%s' from '%s' '%s'."
                  % (volume_type_id, datastore_name, datastore_version_name))
        except Exception as e:
            print(e)

    def datastore_version_volume_type_list(self, datastore_name,
                                           datastore_version_name,
                                           version=None):
        """Lists volume type association with a given datastore."""
        try:
            dsmetadata = datastore_models.DatastoreVersionMetadata

            datastore_version_id = dsmetadata.datastore_version_find(
                datastore_name,
                datastore_version_name,
                version_number=version)

            vtlist = dsmetadata. \
                list_datastore_version_volume_type_associations(
                    datastore_version_id)
            if vtlist.count() > 0:
                for volume_type in vtlist:
                    print("Datastore: %s, Version: %s, Volume Type: %s" %
                          (datastore_name, datastore_version_name,
                           volume_type.value))
            else:
                print("No Volume Type Associations found for Datastore: %s, "
                      "Version: %s." %
                      (datastore_name, datastore_version_name))
        except Exception as e:
            print(e)

    def _get_nova_client(self):
        admin_context = TroveContext(
            user_id=CONF.service_credentials.username,
            project_id=CONF.service_credentials.project_id,
            user_domain_name=CONF.service_credentials.user_domain_name)
        return clients.create_nova_client(admin_context)

    def _check_nova_tags_exists(self):
        self.db_api.configure_db()
        check_instance = DBInstance.find_first(
            filters=[DBInstance.compute_instance_id.isnot(None)],
            deleted=False)
        if check_instance and check_instance.compute_instance_id:
            server = self._get_nova_client().servers.get(
                check_instance.compute_instance_id)
            if 'trove_instance' in server.tags:
                return True
        return False

    def set_nova_tags(self, force=None):
        if not force and self._check_nova_tags_exists():
            raise SystemExit(_(
                "Nova tags are already set. Use \"--force true\" flag if you "
                "need to run this operation anyway."))
        """Set tags to nova servers for ALL existing db instances."""
        self.db_api.configure_db()
        nova_client = self._get_nova_client()

        if nova_client.api_version < api_versions.APIVersion('2.26'):
            raise SystemExit(_("Minimal Nova API version 2.26 is required."))

        def _set_server_tags(server, datastore_version):
            current_tags = server.tags or []
            trove_tags = [
                'trove_instance',
                f'trove_{datastore_version.datastore_name}'] + [
                f"{key}_{value}" for key, value in server.metadata.items()]
            tags = list(set(current_tags) | set(trove_tags))
            nova_client.servers.set_tags(server.id, tags)

        for instance in DBInstance.find_all(deleted=False).all():
            if instance.compute_instance_id:
                try:
                    server = nova_client.servers.get(
                        instance.compute_instance_id)
                    dv = datastore_models.DatastoreVersion.load_by_uuid(
                        instance.datastore_version_id)
                    _set_server_tags(server, dv)

                    print("Tags were updated for server: %s (instance %s)" %
                          (server.id, instance.id))
                except Exception as e:
                    print('Error occured while setting nova tags for server '
                          '%s', server.id)
                    print(e)

    def params_of(self, command_name):
        if Commands.has(command_name):
            return utils.MethodInspector(getattr(self, command_name))


def main():

    def actions(subparser):
        repo_path_help = 'SQLAlchemy Migrate repository path.'

        parser = subparser.add_parser(
            'db_sync', description='Populate the database structure')
        parser.add_argument('--repo_path', help=repo_path_help)

        parser = subparser.add_parser(
            'db_upgrade', description='Upgrade the database to the '
            'specified version.')
        parser.add_argument(
            '--version', help='Target version. Defaults to the '
            'latest version.')
        parser.add_argument('--repo_path', help=repo_path_help)

        parser = subparser.add_parser(
            'datastore_update', description='Add or update a datastore. '
            'If the datastore already exists, the default version will be '
            'updated.')
        parser.add_argument(
            'datastore_name', help='Name of the datastore.')
        parser.add_argument(
            'default_version', help='Name or ID of an existing datastore '
            'version to set as the default. When adding a new datastore, use '
            'an empty string.')

        parser = subparser.add_parser(
            'datastore_version_update', description='Add or update a '
            'datastore version. If the datastore version already exists, all '
            'values except the datastore name and version will be updated.')
        parser.add_argument('datastore', help='Name of the datastore.')
        parser.add_argument(
            'version_name', help='Name of the datastore version.')
        parser.add_argument(
            'manager', help='Name of the manager that will administer the '
            'datastore version.')
        parser.add_argument(
            'image_id',
            help='ID of the image used to create an instance of '
                 'the datastore version.')
        parser.add_argument(
            '--registry-ext',
            help='Extension for default datastore managers. '
            'Allows the use of custom managers for each of '
            'the datastores supported by Trove.')
        parser.add_argument(
            '--repl-strategy',
            help='Extension for default strategy for replication. '
            'Allows the use of custom managers for each of '
            'the datastores supported by Trove.')
        parser.add_argument(
            'packages', help='Packages required by the datastore version that '
            'are installed on the guest image.')
        parser.add_argument(
            'active', type=int,
            help='Whether the datastore version is active or not. '
            'Accepted values are 0 and 1.')
        parser.add_argument(
            '--image-tags',
            help='List of image tags separated by comma used for getting '
                 'guest image.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <version_name> as default value.')

        parser = subparser.add_parser(
            'db_recreate', description='Drop the database and recreate it.')
        parser.add_argument('--repo_path', help=repo_path_help)

        parser = subparser.add_parser(
            'db_load_datastore_config_parameters',
            description='Loads configuration group parameter validation rules '
            'for a datastore version into the database.')
        parser.add_argument(
            'datastore',
            help='Name of the datastore.')
        parser.add_argument(
            'datastore_version_name',
            help='Name of the datastore version.')
        parser.add_argument(
            'config_file_location',
            help='Fully qualified file path to the configuration group '
            'parameter validation rules.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'db_remove_datastore_config_parameters',
            description='Remove configuration group parameter validation '
                        'rules for a datastore version from the database.')
        parser.add_argument(
            'datastore',
            help='Name of the datastore.')
        parser.add_argument(
            'datastore_version_name',
            help='Name of the datastore version.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'datastore_version_flavor_add',
            help='Adds flavor association to a given datastore and datastore '
                 'version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument('flavor_ids', help='Comma separated list of '
                            'flavor ids.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'datastore_version_flavor_delete',
            help='Deletes a flavor associated with a given datastore and '
                 'datastore version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument('flavor_id', help='The flavor to be deleted for '
                            'a given datastore and datastore version.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'datastore_version_volume_type_add',
            help='Adds volume_type association to a given datastore and '
                 'datastore version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument('volume_type_ids', help='Comma separated list of '
                            'volume_type ids.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'datastore_version_volume_type_delete',
            help='Deletes a volume_type '
                 'associated with a given datastore and datastore version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument('volume_type_id', help='The volume_type to be '
                            'deleted for a given datastore and datastore '
                            'version.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'datastore_version_volume_type_list',
            help='Lists the volume_types '
                 'associated with a given datastore and datastore version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument(
            '--version',
            help='The version number of the datastore version, e.g. 5.7.30. '
                 'If not specified, use <datastore_version_name> as default '
                 'value.')

        parser = subparser.add_parser(
            'set_nova_tags',
            description='Set required tags for ALL nova servers in service '
                        'project. Run this when upgrading from versions '
                        'prior to 2026.2')
        parser.add_argument(
            '--force',
            help='Force setting nova tags, replacing existing tags. The '
                 'operation is idempotent and will keep existing tags.')

    cfg.custom_parser('action', actions)
    cfg.parse_args(sys.argv)

    try:
        logging.setup(CONF, None)

        Commands().execute()
        sys.exit(0)
    except TypeError as e:
        print(_("Possible wrong number of arguments supplied %s.") % e)
        sys.exit(2)
    except Exception:
        print(_("Command failed, please check log for more info."))
        raise
