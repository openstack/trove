# Copyright 2015 Tesora Inc.
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

import abc
import os
import re
import six

from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode


class ConfigurationManager(object):
    """
    ConfigurationManager is responsible for management of
    datastore configuration.
    Its base functionality includes reading and writing configuration files.
    It is responsible for validating user inputs and requests.
    When supplied an override strategy it allows the user to manage
    configuration overrides as well.
    """

    # Configuration group names. The names determine the order in which the
    # groups get applied. System group should get applied over the user group.
    USER_GROUP = '20-user'
    SYSTEM_GROUP = '50-system'

    DEFAULT_STRATEGY_OVERRIDES_SUB_DIR = 'overrides'
    DEFAULT_CHANGE_ID = 'common'

    def __init__(self, base_config_path, owner, group, codec,
                 requires_root=False, override_strategy=None):
        """
        :param base_config_path     Path to the configuration file.
        :type base_config_path      string

        :param owner                Owner of the configuration files.
        :type owner                 string

        :param group                Group of the configuration files.
        :type group                 string

        :param codec                Codec for reading/writing of the particular
                                    configuration format.
        :type codec                 StreamCodec

        :param requires_root        Whether the manager requires superuser
                                    privileges.
        :type requires_root         boolean

        :param override_strategy    Strategy used to manage configuration
                                    overrides (e.g. ImportOverrideStrategy).
                                    Defaults to OneFileOverrideStrategy
                                    if None. This strategy should be
                                    compatible with very much any datastore.
                                    It is recommended each datastore defines
                                    its strategy explicitly to avoid upgrade
                                    compatibility issues in case the default
                                    implementation changes in the future.
        :type override_strategy     ConfigurationOverrideStrategy
        """
        self._base_config_path = base_config_path
        self._owner = owner
        self._group = group
        self._codec = codec
        self._requires_root = requires_root
        self._value_cache = None

        if not override_strategy:
            # Use OneFile strategy by default. Store the revisions in a
            # sub-directory at the location of the configuration file.
            revision_dir = guestagent_utils.build_file_path(
                os.path.dirname(base_config_path),
                self.DEFAULT_STRATEGY_OVERRIDES_SUB_DIR)
            self._override_strategy = OneFileOverrideStrategy(revision_dir)
        else:
            self._override_strategy = override_strategy

        self._override_strategy.configure(
            base_config_path, owner, group, codec, requires_root)

    def get_value(self, key, default=None):
        """Return the current value at a given key or 'default'.
        """
        if self._value_cache is None:
            self._refresh_cache()

        return self._value_cache.get(key, default)

    def parse_configuration(self):
        """Read contents of the configuration file (applying overrides if any)
        and parse it into a dict.

        :returns:        Configuration file as a Python dict.
        """

        base_options = operating_system.read_file(
            self._base_config_path, codec=self._codec,
            as_root=self._requires_root)

        updates = self._override_strategy.parse_updates()
        guestagent_utils.update_dict(updates, base_options)

        return base_options

    def save_configuration(self, options):
        """Write given contents to the base configuration file.
        Remove all existing overrides (both system and user).

        :param contents        Contents of the configuration file.
        :type contents         string or dict
        """
        if isinstance(options, dict):
            # Serialize a dict of options for writing.
            self.save_configuration(self._codec.serialize(options))
        else:
            self._override_strategy.remove(self.USER_GROUP)
            self._override_strategy.remove(self.SYSTEM_GROUP)

            operating_system.write_file(
                self._base_config_path, options, as_root=self._requires_root)
            operating_system.chown(
                self._base_config_path, self._owner, self._group,
                as_root=self._requires_root)
            operating_system.chmod(
                self._base_config_path, FileMode.ADD_READ_ALL,
                as_root=self._requires_root)

            self._refresh_cache()

    def has_system_override(self, change_id):
        """Return whether a given 'system' change exists.
        """
        return self._override_strategy.exists(self.SYSTEM_GROUP, change_id)

    def apply_system_override(self, options, change_id=DEFAULT_CHANGE_ID):
        """Apply a 'system' change to the configuration.

        System overrides are always applied after all user changes so that
        they override any user-defined setting.

        :param options        Configuration changes.
        :type options         string or dict
        """
        self._apply_override(self.SYSTEM_GROUP, change_id, options)

    def apply_user_override(self, options, change_id=DEFAULT_CHANGE_ID):
        """Apply a 'user' change to the configuration.

        The 'system' values will be re-applied over this override.

        :param options        Configuration changes.
        :type options         string or dict
        """
        self._apply_override(self.USER_GROUP, change_id, options)

    def get_user_override(self, change_id=DEFAULT_CHANGE_ID):
        """Get the user overrides"""
        return self._override_strategy.get(self.USER_GROUP, change_id)

    def _apply_override(self, group_name, change_id, options):
        if not isinstance(options, dict):
            # Deserialize the options into a dict if not already.
            self._apply_override(
                group_name, change_id, self._codec.deserialize(options))
        else:
            self._override_strategy.apply(group_name, change_id, options)
            self._refresh_cache()

    def remove_system_override(self, change_id=DEFAULT_CHANGE_ID):
        """Revert a 'system' configuration change.
        """
        self._remove_override(self.SYSTEM_GROUP, change_id)

    def remove_user_override(self, change_id=DEFAULT_CHANGE_ID):
        """Revert a 'user' configuration change.
        """
        self._remove_override(self.USER_GROUP, change_id)

    def _remove_override(self, group_name, change_id):
        self._override_strategy.remove(group_name, change_id)
        self._refresh_cache()

    def _refresh_cache(self):
        self._value_cache = self.parse_configuration()


@six.add_metaclass(abc.ABCMeta)
class ConfigurationOverrideStrategy(object):
    """ConfigurationOverrideStrategy handles configuration files.
    The strategy provides functionality to enumerate, apply and remove
    configuration overrides.
    """

    @abc.abstractmethod
    def configure(self, *args, **kwargs):
        """Configure this strategy.
        A strategy needs to be configured before it can be used.
        It would typically be configured by the ConfigurationManager.
        """

    @abc.abstractmethod
    def exists(self, group_name, change_id):
        """Return whether a given revision exists.
        """

    @abc.abstractmethod
    def apply(self, group_name, change_id, options):
        """Apply given options on the most current configuration revision.
        Update if a file with the same id already exists.

        :param group_name        The group the override belongs to.
        :type group_name         string

        :param change_id         The name of the override within the group.
        :type change_id          string

        :param options           Configuration changes.
        :type options            dict
        """

    @abc.abstractmethod
    def remove(self, group_name, change_id=None):
        """Rollback a given configuration override.
        Remove the whole group if 'change_id' is None.

        :param group_name        The group the override belongs to.
        :type group_name         string

        :param change_id         The name of the override within the group.
        :type change_id          string
        """

    @abc.abstractmethod
    def get(self, group_name, change_id=None):
        """Return the contents of a given configuration override

        :param group_name        The group the override belongs to.
        :type group_name         string

        :param change_id         The name of the override within the group.
        :type change_id          string
        """

    def parse_updates(self):
        """Return all updates applied to the base revision as a single dict.
        Return an empty dict if the base file is always the most current
        version of configuration.

        :returns:        Updates to the base revision as a Python dict.
        """
        return {}


class ImportOverrideStrategy(ConfigurationOverrideStrategy):
    """Import strategy keeps overrides in separate files that get imported
    into the base configuration file which never changes itself.
    An override file is simply deleted when the override is removed.

    We keep two sets of override files in a separate directory.
     - User overrides - configuration overrides applied by the user via the
       Trove API.
     - System overrides - 'internal' configuration changes applied by the
       guestagent.

    The name format of override files is: '<set prefix>-<n>-<group name>.<ext>'
    where 'set prefix' is to used to order user/system sets,
    'n' is an index used to keep track of the order in which overrides
    within their set got applied.
    """

    FILE_NAME_PATTERN = '%s-([0-9]+)-%s\.%s$'

    def __init__(self, revision_dir, revision_ext):
        """
        :param revision_dir  Path to the directory for import files.
        :type revision_dir   string

        :param revision_ext  Extension of revision files.
        :type revision_ext   string
        """
        self._revision_dir = revision_dir
        self._revision_ext = revision_ext

    def configure(self, base_config_path, owner, group, codec, requires_root):
        """
        :param base_config_path     Path to the configuration file.
        :type base_config_path      string

        :param owner                Owner of the configuration and
                                    revision files.
        :type owner                 string

        :param group                Group of the configuration and
                                    revision files.
        :type group                 string

        :param codec                Codec for reading/writing of the particular
                                    configuration format.
        :type codec                 StreamCodec

        :param requires_root        Whether the strategy requires superuser
                                    privileges.
        :type requires_root         boolean
        """
        self._base_config_path = base_config_path
        self._owner = owner
        self._group = group
        self._codec = codec
        self._requires_root = requires_root

    def exists(self, group_name, change_id):
        return self._find_revision_file(group_name, change_id) is not None

    def apply(self, group_name, change_id, options):
        self._initialize_import_directory()
        revision_file = self._find_revision_file(group_name, change_id)
        if revision_file is None:
            # Create a new file.
            last_revision_index = self._get_last_file_index(group_name)
            revision_file = guestagent_utils.build_file_path(
                self._revision_dir,
                '%s-%03d-%s' % (group_name, last_revision_index + 1,
                                change_id),
                self._revision_ext)
        else:
            # Update the existing file.
            current = operating_system.read_file(
                revision_file, codec=self._codec, as_root=self._requires_root)
            options = guestagent_utils.update_dict(options, current)

        operating_system.write_file(
            revision_file, options, codec=self._codec,
            as_root=self._requires_root)
        operating_system.chown(
            revision_file, self._owner, self._group,
            as_root=self._requires_root)
        operating_system.chmod(
            revision_file, FileMode.ADD_READ_ALL, as_root=self._requires_root)

    def _initialize_import_directory(self):
        """Lazy-initialize the directory for imported revision files.
        """
        if not os.path.exists(self._revision_dir):
            operating_system.create_directory(
                self._revision_dir, user=self._owner, group=self._group,
                force=True, as_root=self._requires_root)

    def remove(self, group_name, change_id=None):
        removed = set()
        if change_id:
            # Remove a given file.
            revision_file = self._find_revision_file(group_name, change_id)
            if revision_file:
                removed.add(revision_file)
        else:
            # Remove the entire group.
            removed = self._collect_revision_files(group_name)

        for path in removed:
            operating_system.remove(path, force=True,
                                    as_root=self._requires_root)

    def get(self, group_name, change_id):
        revision_file = self._find_revision_file(group_name, change_id)

        return operating_system.read_file(revision_file,
                                          codec=self._codec,
                                          as_root=self._requires_root)

    def parse_updates(self):
        parsed_options = {}
        for path in self._collect_revision_files():
            options = operating_system.read_file(path, codec=self._codec,
                                                 as_root=self._requires_root)
            guestagent_utils.update_dict(options, parsed_options)

        return parsed_options

    @property
    def has_revisions(self):
        """Return True if there currently are any revision files.
        """
        return (operating_system.exists(
            self._revision_dir, is_directory=True,
            as_root=self._requires_root) and
            (len(self._collect_revision_files()) > 0))

    def _get_last_file_index(self, group_name):
        """Get the index of the most current file in a given group.
        """
        current_files = self._collect_revision_files(group_name)
        if current_files:
            name_pattern = self._build_rev_name_pattern(group_name=group_name)
            last_file_name = os.path.basename(current_files[-1])
            last_index_match = re.match(name_pattern, last_file_name)
            if last_index_match:
                return int(last_index_match.group(1))

        return 0

    def _collect_revision_files(self, group_name='.+'):
        """Collect and return a sorted list of paths to existing revision
        files. The files should be sorted in the same order in which
        they were applied.
        """
        name_pattern = self._build_rev_name_pattern(group_name=group_name)
        return sorted(operating_system.list_files_in_directory(
            self._revision_dir, recursive=True, pattern=name_pattern,
            as_root=self._requires_root))

    def _find_revision_file(self, group_name, change_id):
        name_pattern = self._build_rev_name_pattern(group_name, change_id)
        found = operating_system.list_files_in_directory(
            self._revision_dir, recursive=True, pattern=name_pattern,
            as_root=self._requires_root)
        return next(iter(found), None)

    def _build_rev_name_pattern(self, group_name='.+', change_id='.+'):
        return self.FILE_NAME_PATTERN % (group_name, change_id,
                                         self._revision_ext)


class OneFileOverrideStrategy(ConfigurationOverrideStrategy):
    """This is a strategy for datastores that do not support multiple
    configuration files.
    It uses the Import Strategy to keep the overrides internally.
    When an override is applied or removed a new configuration file is
    generated by applying all changes on a saved-off base revision.
    """

    BASE_REVISION_NAME = 'base'
    REVISION_EXT = 'rev'

    def __init__(self, revision_dir):
        """
        :param revision_dir  Path to the directory for import files.
        :type revision_dir   string
        """
        self._revision_dir = revision_dir
        self._import_strategy = ImportOverrideStrategy(revision_dir,
                                                       self.REVISION_EXT)

    def configure(self, base_config_path, owner, group, codec, requires_root):
        """
        :param base_config_path     Path to the configuration file.
        :type base_config_path      string

        :param owner                Owner of the configuration and
                                    revision files.
        :type owner                 string

        :param group                Group of the configuration and
                                    revision files.
        :type group                 string

        :param codec                Codec for reading/writing of the particular
                                    configuration format.
        :type codec                 StreamCodec

        :param requires_root        Whether the strategy requires superuser
                                    privileges.
        :type requires_root         boolean
        """
        self._base_config_path = base_config_path
        self._owner = owner
        self._group = group
        self._codec = codec
        self._requires_root = requires_root
        self._base_revision_file = guestagent_utils.build_file_path(
            self._revision_dir, self.BASE_REVISION_NAME, self.REVISION_EXT)

        self._import_strategy.configure(
            base_config_path, owner, group, codec, requires_root)

    def exists(self, group_name, change_id):
        return self._import_strategy.exists(group_name, change_id)

    def apply(self, group_name, change_id, options):
        self._import_strategy.apply(group_name, change_id, options)
        self._regenerate_base_configuration()

    def remove(self, group_name, change_id=None):
        if self._import_strategy.has_revisions:
            self._import_strategy.remove(group_name, change_id=change_id)
            self._regenerate_base_configuration()
            if not self._import_strategy.has_revisions:
                # The base revision file is no longer needed if there are no
                # overrides. It will be regenerated based on the current
                # configuration file on the first 'apply()'.
                operating_system.remove(self._base_revision_file, force=True,
                                        as_root=self._requires_root)

    def get(self, group_name, change_id):
        return self._import_strategy.get(group_name, change_id)

    def _regenerate_base_configuration(self):
        """Gather all configuration changes and apply them in order on the base
        revision. Write the results to the configuration file.
        """

        if not os.path.exists(self._base_revision_file):
            # Initialize the file with the current configuration contents if it
            # does not exist.
            operating_system.copy(
                self._base_config_path, self._base_revision_file,
                force=True, preserve=True, as_root=self._requires_root)

        base_revision = operating_system.read_file(
            self._base_revision_file, codec=self._codec,
            as_root=self._requires_root)
        changes = self._import_strategy.parse_updates()
        updated_revision = guestagent_utils.update_dict(changes, base_revision)
        operating_system.write_file(
            self._base_config_path, updated_revision, codec=self._codec,
            as_root=self._requires_root)
