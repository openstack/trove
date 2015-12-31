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

import gettext
import inspect
import sys


gettext.install('trove', unicode=1)


from oslo_log import log as logging
from oslo_log.versionutils import deprecated

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.configuration import models as config_models
from trove.datastore import models as datastore_models
from trove.db import get_db_api


CONF = cfg.CONF


class Commands(object):

    def __init__(self):
        self.db_api = get_db_api()

    def db_sync(self, repo_path=None):
        self.db_api.db_sync(CONF, repo_path=repo_path)

    def db_upgrade(self, version=None, repo_path=None):
        self.db_api.db_upgrade(CONF, version, repo_path=repo_path)

    @deprecated(as_of=deprecated.MITAKA)
    def db_downgrade(self, version, repo_path=None):
        self.db_api.db_downgrade(CONF, version, repo_path=repo_path)

    def execute(self):
        exec_method = getattr(self, CONF.action.name)
        args = inspect.getargspec(exec_method)
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
                                 image_id, packages, active):
        try:
            datastore_models.update_datastore_version(datastore,
                                                      version_name,
                                                      manager,
                                                      image_id,
                                                      packages, active)
            print("Datastore version '%s' updated." % version_name)
        except exception.DatastoreNotFound as e:
            print(e)

    def db_recreate(self, repo_path):
        """Drops the database and recreates it."""
        self.db_api.drop_db(CONF)
        self.db_sync(repo_path)

    def db_load_datastore_config_parameters(self,
                                            datastore,
                                            datastore_version,
                                            config_file_location):
        print("Loading config parameters for datastore (%s) version (%s)"
              % (datastore, datastore_version))
        config_models.load_datastore_configuration_parameters(
            datastore, datastore_version, config_file_location)

    def datastore_version_flavor_add(self, datastore_name,
                                     datastore_version_name, flavor_ids):
        """Adds flavors for a given datastore version id."""
        try:
            dsmetadata = datastore_models.DatastoreVersionMetadata
            dsmetadata.add_datastore_version_flavor_association(
                datastore_name, datastore_version_name, flavor_ids.split(","))
            print("Added flavors '%s' to the '%s' '%s'."
                  % (flavor_ids, datastore_name, datastore_version_name))
        except exception.DatastoreVersionNotFound as e:
            print(e)

    def datastore_version_flavor_delete(self, datastore_name,
                                        datastore_version_name, flavor_id):
        """Deletes a flavor's association with a given datastore."""
        try:
            dsmetadata = datastore_models.DatastoreVersionMetadata
            dsmetadata.delete_datastore_version_flavor_association(
                datastore_name, datastore_version_name, flavor_id)
            print("Deleted flavor '%s' from '%s' '%s'."
                  % (flavor_id, datastore_name, datastore_version_name))
        except exception.DatastoreVersionNotFound as e:
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
            'db_downgrade', description='Downgrade the database to the '
            'specified version.')
        parser.add_argument('version', help='Target version.')
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
            'image_id', help='ID of the image used to create an instance of '
            'the datastore version.')
        parser.add_argument(
            'packages', help='Packages required by the datastore version that '
            'are installed on the guest image.')
        parser.add_argument(
            'active', help='Whether the datastore version is active or not. '
            'Accepted values are 0 and 1.')

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
            'datastore_version',
            help='Name of the datastore version.')
        parser.add_argument(
            'config_file_location',
            help='Fully qualified file path to the configuration group '
            'parameter validation rules.')

        parser = subparser.add_parser(
            'datastore_version_flavor_add', help='Adds flavor association to '
            'a given datastore and datastore version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument('flavor_ids', help='Comma separated list of '
                            'flavor ids.')

        parser = subparser.add_parser(
            'datastore_version_flavor_delete', help='Deletes a flavor '
            'associated with a given datastore and datastore version.')
        parser.add_argument('datastore_name', help='Name of the datastore.')
        parser.add_argument('datastore_version_name', help='Name of the '
                            'datastore version.')
        parser.add_argument('flavor_id', help='The flavor to be deleted for '
                            'a given datastore and datastore version.')
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
