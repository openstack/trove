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
import six

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode

CONF = cfg.CONF
MANAGER = CONF.datastore_manager


class ConfigurationError(exception.TroveError):

    def __init__(self, msg):
        super(ConfigurationError, self).__init__(msg)


class ConfigurationManager(object):
    """
    ConfigurationManager is responsible for management of
    datastore configuration.
    Its base functionality includes reading and writing configuration files.
    It is responsible for validating user inputs and requests.
    When supplied an override strategy it allows the user to manage
    configuration overrides as well.
    """

    def __init__(self, base_config_path, owner, group, codec,
                 requires_root=False):
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
        """
        self._base_config_path = base_config_path
        self._owner = owner
        self._group = group
        self._codec = codec
        self._requires_root = requires_root

        self._current_revision = 0
        self._max_num_overrides = 0
        self._override_strategy = None

    @property
    def override_strategy(self):
        return self._override_strategy

    @override_strategy.setter
    def override_strategy(self, value):
        if value:
            value.configure(
                self._base_config_path, self._owner, self._group, self._codec,
                self._requires_root)
            # The 'system' revision does not count, hence '-1'.
            self._current_revision = max(value.count_revisions() - 1, 0)
        else:
            self._current_revision = 0

        self._max_num_overrides = 0
        self._override_strategy = value

    @property
    def current_revision(self):
        return self._current_revision

    @property
    def max_num_overrides(self):
        return self._max_num_overrides

    @max_num_overrides.setter
    def max_num_overrides(self, value):
        """
        Maximum number of configuration overrides that can be attached to this
        instance.
        """
        if value and value < 0:
            raise exception.UnprocessableEntity(
                _("The maximum number of attached Configuration Groups "
                  "cannot be negative."))
        self._max_num_overrides = value

    def set_override_strategy(self, strategy, max_num_overrides=1):
        """Set a strategy for management of configuration overrides.
        """
        self.override_strategy = strategy
        self.max_num_overrides = max_num_overrides

    def parse_configuration(self):
        """Read contents of the configuration file (applying overrides if any)
        and parse it into a dict.

        :returns:        Configuration file as a Python dict.
        """

        base_options = operating_system.read_file(
            self._base_config_path, codec=self._codec)

        if self._override_strategy:
            updates = self._override_strategy.parse_updates()
            guestagent_utils.update_dict(updates, base_options)

        return base_options

    def get_value(self, key, default=None):
        """Return value at a given key or 'default'.
        """
        config = self.parse_configuration()
        return config.get(key, default)

    def save_configuration(self, contents):
        """Write given contents to the base configuration file.
        Remove all existing revisions.

        :param contents        Plain-text contents of the configuration file.
        :type contents         string
        """
        if self._override_strategy:
            self._override_strategy.remove_last(self._current_revision + 1)

        operating_system.write_file(
            self._base_config_path, contents, as_root=self._requires_root)
        operating_system.chown(
            self._base_config_path, self._owner, self._group,
            as_root=self._requires_root)
        operating_system.chmod(
            self._base_config_path, FileMode.ADD_READ_ALL,
            as_root=self._requires_root)

    def render_configuration(self, options):
        """Write contents to the base configuration file.
        Remove all existing revisions.

        :param options        Configuration options.
        :type options         dict
        """
        self.save_configuration(self._codec.serialize(options))

    def update_configuration(self, options):
        """Update given options in the configuration.

        The updates are stored in a 'system' revision if the manager
        supports configuration overrides. Otherwise they get applied
        directly to the base configuration file.

        The 'system' revision is always applied last to ensure it
        overrides any user-specified configuration changes.
        """
        if self._override_strategy:
            # Update the system overrides.
            system_overrides = self._override_strategy.get(
                self._current_revision + 1)
            guestagent_utils.update_dict(options, system_overrides)
            # Re-apply the updated system overrides.
            self._override_strategy.remove_last(1)
            self._override_strategy.apply_next(system_overrides)
        else:
            # Update the base configuration file.
            config = self.parse_configuration()
            guestagent_utils.update_dict(options, config)
            self.render_configuration(config)

    def update_override(self, contents):
        """Same as 'apply_override' but accepts serialized
        input.

        :param contents        Plain-text contents of the configuration file.
        :type contents         string
        """
        self.apply_override(self._codec.deserialize(contents))

    def apply_override(self, options):
        """Update given options of the current configuration. The 'system'
        values will be re-applied over this override.

        :raises:    :class:`ConfigurationError` if the maximum number of
                            overrides attached to this instance is exceeded.
        """
        if self._override_strategy:
            if self._current_revision < self.max_num_overrides:
                # Save off the 'system' overrides and remove the revision file.
                # apply the user-options and re-apply the system values
                # on the top of it.
                system_overrides = self._override_strategy.get(
                    self._current_revision + 1)
                self._override_strategy.remove_last(1)
                self._override_strategy.apply_next(options)
                self._override_strategy.apply_next(system_overrides)
                self._current_revision = self._current_revision + 1
            else:
                raise ConfigurationError(
                    _("This instance cannot have more than '%d' "
                      "Configuration Groups attached.")
                    % self.max_num_overrides)
        else:
            raise exception.DatastoreOperationNotSupported(
                operation='update_overrides', datastore=MANAGER)

    def remove_override(self):
        """Revert the last configuration override. This does not include the
        'system' overrides.

        :raises:    :class:`ConfigurationError` if there are currently no
                            overrides attached to this instance.
        """
        if self._override_strategy:
            if self._current_revision > 0:
                # Save off the 'system' overrides, rollback the last two
                # revisions (system + the last user-defined override) and
                # re-apply the system values.
                system_overrides = self._override_strategy.get(
                    self._current_revision + 1)
                self._override_strategy.remove_last(2)
                self._override_strategy.apply_next(system_overrides)
                self._current_revision = self._current_revision - 1
            else:
                raise ConfigurationError(
                    _("This instance does not have a Configuration Group "
                      "attached."))
        else:
            raise exception.DatastoreOperationNotSupported(
                operation='update_overrides', datastore=MANAGER)


@six.add_metaclass(abc.ABCMeta)
class ConfigurationOverrideStrategy(object):
    """ConfigurationOverrideStrategy handles configuration files.
    The strategy provides functionality to enumerate, apply and remove
    configuration overrides (revisions).
    """

    @abc.abstractmethod
    def configure(self, *args, **kwargs):
        """Configure this strategy.
        A strategy needs to be configured before it can be used.
        It would typically be configured by the ConfigurationManager.
        """

    def count_revisions(self):
        """Return the number of existing revisions.
        """
        return len(self._collect_revisions())

    @abc.abstractmethod
    def apply_next(self, options):
        """Apply given options on the current revision.
        """

    @abc.abstractmethod
    def remove_last(self, num_revisions):
        """Rollback the last 'num_revisions' of revisions.

        :param num_revisions        Number of last revisions to rollback.
                                    Rollback all if it is greater or
                                    equal to the number of existing revisions.
        :type num_revisions         int
        """

    def _list_all_files(self, root_dir, pattern):
        return operating_system.list_files_in_directory(
            root_dir, recursive=False, pattern=pattern)

    def parse_updates(self):
        """Return all updates applied to the base revision as a single dict.
        Return an empty dict if the base file is always the most current
        version of configuration.

        :returns:        Updates to the base revision s as a Python dict.
        """
        return {}

    @abc.abstractmethod
    def get(self, revision):
        """Return parsed contents of a given revision.

        :returns:        Contents of the last revision file as a Python dict.
        """

    @abc.abstractmethod
    def _collect_revisions(self):
        """Collect and return a sorted list of paths to existing revision
        files. The files should be sorted in the same order in which
        they were applied.
        """


class RollingOverrideStrategy(ConfigurationOverrideStrategy):
    """Rolling strategy maintains a single configuration file.
    It applies overrides in-place always backing-up the current revision of
    the file so that it can be restored when the override is removed.
    It appends a revision number to the backup file name so that they
    can be restored in the order opposite to in which they were applied.
    """

    _BACKUP_EXT = 'old'
    _BACKUP_NAME_PATTERN = '^.*\.[1-9]+.%s$' % _BACKUP_EXT

    def __init__(self, revision_backup_dir):
        """
        :param revision_backup_dir  Path to the directory for revision
                                    backups.
        :type revision_backup_dir   string
        """
        self._revision_backup_dir = revision_backup_dir

    def configure(self, base_config_path, owner, group, codec, requires_root):
        """
        :param base_config_path     Path to the configuration file.
        :type base_config_path      string

        :param owner                Owner of the configuration and
                                    backup files.
        :type owner                 string

        :param group                Group of the configuration and
                                    backup files.
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
        self._base_config_name = os.path.basename(base_config_path)

    def apply_next(self, options):
        revision_num = self.count_revisions() + 1
        old_revision_backup = guestagent_utils.build_file_path(
            self._revision_backup_dir, self._base_config_name,
            str(revision_num), self._BACKUP_EXT)
        operating_system.copy(self._base_config_path, old_revision_backup,
                              force=True, preserve=True,
                              as_root=self._requires_root)
        current = operating_system.read_file(self._base_config_path,
                                             codec=self._codec)
        guestagent_utils.update_dict(options, current)
        operating_system.write_file(
            self._base_config_path, current, codec=self._codec,
            as_root=self._requires_root)
        operating_system.chown(
            self._base_config_path, self._owner, self._group,
            as_root=self._requires_root)
        operating_system.chmod(
            self._base_config_path, FileMode.ADD_READ_ALL,
            as_root=self._requires_root)

    def remove_last(self, num_revisions):
        count = self.count_revisions()
        revision_files = self._delete_revisions(min(count, num_revisions) - 1)
        if revision_files:
            operating_system.move(revision_files[-1], self._base_config_path,
                                  force=True, as_root=self._requires_root)

    def _delete_revisions(self, num_revisions):
        revision_files = self._collect_revisions()
        deleted_files = []
        if num_revisions > 0:
            deleted_files = revision_files[-num_revisions:]
            for path in deleted_files:
                operating_system.remove(path, force=True,
                                        as_root=self._requires_root)

        return [path for path in revision_files if path not in deleted_files]

    def get(self, revision):
        revisions = self._collect_revisions()
        if revisions:
            # Return the difference between this revision and the current base.
            this_revision = operating_system.read_file(
                revisions[revision - 1], codec=self._codec)
            current_base = operating_system.read_file(
                self._base_config_path, codec=self._codec)

            return guestagent_utils.dict_difference(this_revision,
                                                    current_base)

        return {}

    def _collect_revisions(self):
        return sorted(self._list_all_files(
            self._revision_backup_dir, self._BACKUP_NAME_PATTERN))


class ImportOverrideStrategy(ConfigurationOverrideStrategy):
    """Import strategy keeps overrides in separate files that get imported
    into the base configuration file which never changes itself.
    An override file is simply deleted when the override is removed.
    It appends a revision number to the backup file name so that they
    can be restored in the order opposite to in which they were applied.
    """

    def __init__(self, revision_dir, revision_ext):
        """
        :param revision_dir  Path to the directory for import files.
        :type revision_dir   string

        :param revision_ext  Extension of revision files.
        :type revision_ext   string
        """
        self._revision_dir = revision_dir
        self._revision_ext = revision_ext
        self._import_name_pattern = '^.*\.[1-9]+.%s$' % revision_ext

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
        self._base_config_name = os.path.basename(base_config_path)

    def apply_next(self, options):
        revision_num = self.count_revisions() + 1
        revision_file_path = guestagent_utils.build_file_path(
            self._revision_dir, self._base_config_name, str(revision_num),
            self._revision_ext)
        operating_system.write_file(
            revision_file_path, options,
            codec=self._codec, as_root=self._requires_root)
        operating_system.chown(revision_file_path, self._owner, self._group,
                               as_root=self._requires_root)
        operating_system.chmod(revision_file_path, FileMode.ADD_READ_ALL,
                               as_root=self._requires_root)

    def remove_last(self, num_revisions):
        revision_files = self._collect_revisions()
        deleted_files = []
        if num_revisions > 0:
            deleted_files = revision_files[-num_revisions:]
            for path in deleted_files:
                operating_system.remove(path, force=True,
                                        as_root=self._requires_root)

    def get(self, revision):
        revision_files = self._collect_revisions()
        if revision_files:
            revision_file = revision_files[revision - 1]
            return operating_system.read_file(revision_file, codec=self._codec)

        return {}

    def parse_updates(self):
        parsed_options = {}
        for path in self._collect_revisions():
            options = operating_system.read_file(path, codec=self._codec)
            guestagent_utils.update_dict(options, parsed_options)

        return parsed_options

    def _collect_revisions(self):
        return sorted(self._list_all_files(
            self._revision_dir, self._import_name_pattern))
