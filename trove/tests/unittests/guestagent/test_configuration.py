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

import getpass
from mock import DEFAULT
from mock import MagicMock
from mock import Mock
from mock import patch
import os
import tempfile
from testtools.testcase import ExpectedException
from trove.common import exception
from trove.common.stream_codecs import IniCodec
from trove.guestagent.common.configuration import ConfigurationError
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.common.configuration import RollingOverrideStrategy
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.tests.unittests import trove_testtools


class TestConfigurationManager(trove_testtools.TestCase):

    @patch.multiple('trove.guestagent.common.operating_system',
                    read_file=DEFAULT, write_file=DEFAULT,
                    chown=DEFAULT, chmod=DEFAULT)
    def test_read_write_configuration(self, read_file, write_file,
                                      chown, chmod):
        sample_path = Mock()
        sample_owner = Mock()
        sample_group = Mock()
        sample_codec = MagicMock()
        sample_requires_root = Mock()

        manager = ConfigurationManager(
            sample_path, sample_owner, sample_group, sample_codec,
            requires_root=sample_requires_root)

        manager.parse_configuration()
        read_file.assert_called_with(sample_path, codec=sample_codec)

        with patch.object(manager, 'parse_configuration',
                          return_value={'key1': 'v1', 'key2': 'v2'}):
            self.assertEqual('v1', manager.get_value('key1'))
            self.assertEqual(None, manager.get_value('key3'))

        sample_contents = Mock()
        manager.save_configuration(sample_contents)
        write_file.assert_called_with(
            sample_path, sample_contents, as_root=sample_requires_root)

        chown.assert_called_with(sample_path, sample_owner, sample_group,
                                 as_root=sample_requires_root)
        chmod.assert_called_with(
            sample_path, FileMode.ADD_READ_ALL, as_root=sample_requires_root)

        sample_options = Mock()
        with patch.object(manager, 'save_configuration') as save_config:
            manager.render_configuration(sample_options)
            save_config.assert_called_once_with(
                sample_codec.serialize.return_value)
            sample_codec.serialize.assert_called_once_with(sample_options)

        with patch('trove.guestagent.common.configuration.'
                   'ConfigurationOverrideStrategy') as mock_strategy:
            manager.set_override_strategy(mock_strategy)
            manager._current_revision = 3
            manager.save_configuration(sample_contents)
            mock_strategy.remove_last.assert_called_once_with(
                manager._current_revision + 1)
            write_file.assert_called_with(
                sample_path, sample_contents, as_root=sample_requires_root)

    @patch(
        'trove.guestagent.common.configuration.ConfigurationOverrideStrategy')
    def test_configuration_manager(self, mock_strategy):
        mock_strategy.count_revisions.return_value = 0
        manager = ConfigurationManager(Mock(), Mock(), Mock(), Mock())

        with ExpectedException(exception.DatastoreOperationNotSupported):
            manager.update_override({})

        with ExpectedException(exception.DatastoreOperationNotSupported):
            manager.remove_override()

        manager.set_override_strategy(mock_strategy, 1)

        self.assertEqual(1, manager.max_num_overrides)
        self.assertEqual(0, manager.current_revision)

        with ExpectedException(
                exception.UnprocessableEntity,
                "The maximum number of attached Configuration Groups cannot "
                "be negative."):
            manager.max_num_overrides = -1

        manager.max_num_overrides = 2

        self.assertEqual(2, manager.max_num_overrides)

        self.assertEqual(0, manager.current_revision)
        manager.update_override({})
        self.assertEqual(1, manager.current_revision)
        manager.update_override({})
        self.assertEqual(2, manager.current_revision)

        with ExpectedException(
                ConfigurationError, "This instance cannot have more than "
                "'2' Configuration Groups attached."):
            manager.update_override({})

        self.assertEqual(2, manager.current_revision)
        manager.remove_override()
        self.assertEqual(1, manager.current_revision)
        manager.update_override({})
        self.assertEqual(2, manager.current_revision)
        manager.remove_override()
        self.assertEqual(1, manager.current_revision)
        manager.remove_override()
        self.assertEqual(0, manager.current_revision)

        with ExpectedException(
                ConfigurationError,
                "This instance does not have a Configuration Group attached."):
            manager.remove_override()

        self.assertEqual(0, manager.current_revision)

        manager.override_strategy = None

        self.assertEqual(0, manager.max_num_overrides)
        self.assertEqual(0, manager.current_revision)


class TestConfigurationOverrideStrategy(trove_testtools.TestCase):

    def setUp(self):
        trove_testtools.TestCase.setUp(self)
        self._temp_files_paths = []

    def tearDown(self):
        trove_testtools.TestCase.tearDown(self)

        # Remove temprary files in the LIFO order.
        while self._temp_files_paths:
            try:
                os.remove(self._temp_files_paths.pop())
            except Exception:
                pass  # Do not fail in cleanup.

    def _create_temp_dir(self):
        path = tempfile.mkdtemp()
        self._temp_files_paths.append(path)
        return path

    def test_rolling_override_strategy(self):
        base_config_contents = {'Section_1': {'name': 'pi',
                                              'is_number': 'True',
                                              'value': '3.1415'}
                                }

        config_overrides_v1 = {'Section_1': {'name': 'sqrt(2)',
                                             'value': '1.4142'}
                               }

        expected_contents_v1 = {'Section_1': {'name': 'sqrt(2)',
                                              'is_number': 'True',
                                              'value': '1.4142'}
                                }

        config_overrides_v2 = {'Section_1': {'is_number': 'False'}}

        expected_contents_v2 = {'Section_1': {'name': 'sqrt(2)',
                                              'is_number': 'False',
                                              'value': '1.4142'}
                                }

        config_overrides_seq = [config_overrides_v1, config_overrides_v2]
        expected_contents_seq = [base_config_contents, expected_contents_v1,
                                 expected_contents_v2]

        codec = IniCodec()
        current_user = getpass.getuser()
        backup_config_dir = self._create_temp_dir()

        with tempfile.NamedTemporaryFile() as base_config:

            # Write initial config contents.
            operating_system.write_file(
                base_config.name, base_config_contents, codec)

            strategy = RollingOverrideStrategy(backup_config_dir)
            strategy.configure(
                base_config.name, current_user, current_user, codec, False)

            self._assert_rolling_override_strategy(
                strategy, config_overrides_seq, expected_contents_seq)

    def _assert_rolling_override_strategy(
            self, strategy, config_overrides_seq, expected_contents_seq):

        def build_backup_path(revision):
            base_name = os.extsep.join(
                [os.path.basename(strategy._base_config_path),
                 str(revision), 'old'])
            return os.path.join(
                strategy._revision_backup_dir, base_name)

        # Test apply and rollback in sequence.
        ######################################

        # Apply a sequence of overrides.
        for revision, override in enumerate(config_overrides_seq, 1):

            expected_backup_path = build_backup_path(revision)

            # Apply overrides.
            strategy.apply_next(override)

            # Check there is a backup of the old config file.
            self.assertTrue(os.path.exists(expected_backup_path),
                            "Backup revision '%d' does not exist." % revision)

            # Load overriden contents.
            overriden = operating_system.read_file(
                strategy._base_config_path, strategy._codec)

            # Load backed up contents.
            backedup = operating_system.read_file(
                expected_backup_path, strategy._codec)

            # Assert that the config has the overriden contents.
            self.assertEqual(expected_contents_seq[revision], overriden)

            # Assert that the backup matches the previous config contents.
            self.assertEqual(expected_contents_seq[revision - 1], backedup)

        # Rollback the applied overrides.
        for revision, _ in reversed(
                [e for e in enumerate(config_overrides_seq, 1)]):

            expected_backup_path = build_backup_path(revision)

            # Remove last overrides.
            strategy.remove_last(1)

            # Check that the backup was removed.
            self.assertFalse(
                os.path.exists(expected_backup_path),
                "Backup revision '%d' was not removed." %
                revision)

            # Re-load restored contents.
            restored = operating_system.read_file(
                strategy._base_config_path, strategy._codec)

            # Assert that the config was reverted to the previous state.
            self.assertEqual(expected_contents_seq[revision - 1], restored)

        # Test rollback all.
        ####################

        # Apply a sequence of overrides.
        for override in config_overrides_seq:
            strategy.apply_next(override)

        num_revisions = strategy.count_revisions()

        # Check that we have an expected number of revisions.
        self.assertEqual(len(config_overrides_seq), num_revisions)

        # Rollback all revisions at once.
        strategy.remove_last(num_revisions + 1)

        # Check that there are no revisions.
        self.assertEqual(0, strategy.count_revisions())

        # Check that all backups were removed.
        for revision, _ in reversed(
                [e for e in enumerate(config_overrides_seq, 1)]):
            expected_backup_path = build_backup_path(revision)
            self.assertFalse(
                os.path.exists(expected_backup_path),
                "Backup revision '%d' was not removed." % revision)

        # Re-load restored contents.
        restored = operating_system.read_file(
            strategy._base_config_path, strategy._codec)

        # Assert that the config was reverted to the previous state.
        self.assertEqual(expected_contents_seq[0], restored)

    def test_import_override_strategy(self):
        base_config_contents = {'Section_1': {'name': 'pi',
                                              'is_number': 'True',
                                              'value': '3.1415'}
                                }

        config_overrides_v1 = {'Section_1': {'name': 'sqrt(2)',
                                             'value': '1.4142'}
                               }

        config_overrides_v2 = {'Section_1': {'is_number': 'False'}}

        config_overrides_seq = [config_overrides_v1, config_overrides_v2]
        expected_contents_seq = [base_config_contents, base_config_contents,
                                 base_config_contents]

        codec = IniCodec()
        current_user = getpass.getuser()
        revision_dir = self._create_temp_dir()

        with tempfile.NamedTemporaryFile() as base_config:

            # Write initial config contents.
            operating_system.write_file(
                base_config.name, base_config_contents, codec)

            strategy = ImportOverrideStrategy(revision_dir, 'ext')
            strategy.configure(
                base_config.name, current_user, current_user, codec, False)

            self._assert_import_override_strategy(
                strategy, config_overrides_seq, expected_contents_seq)

    def _assert_import_override_strategy(
            self, strategy, config_overrides_seq, expected_contents_seq):

        def build_revision_path(revision):
            base_name = os.extsep.join(
                [os.path.basename(strategy._base_config_path),
                    str(revision), strategy._revision_ext])
            return os.path.join(
                strategy._revision_dir, base_name)

        # Test apply and rollback in sequence.
        ######################################

        # Apply a sequence of overrides.
        for revision, override in enumerate(config_overrides_seq, 1):

            expected_import_path = build_revision_path(revision)

            # Apply overrides.
            strategy.apply_next(override)

            # Check there is a new import file.
            self.assertTrue(os.path.exists(expected_import_path),
                            "Revision import '%d' does not exist." % revision)

            # Load base config contents.
            base = operating_system.read_file(
                strategy._base_config_path, strategy._codec)

            # Load import contents.
            imported = operating_system.read_file(
                expected_import_path, strategy._codec)

            # Assert that the base config did not change.
            self.assertEqual(expected_contents_seq[revision], base)

            # Assert that the import contents match the overrides.
            self.assertEqual(override, imported)

        # Rollback the applied overrides.
        for revision, _ in reversed(
                [e for e in enumerate(config_overrides_seq, 1)]):

            expected_import_path = build_revision_path(revision)

            # Remove last overrides.
            strategy.remove_last(1)

            # Check that the import was removed.
            self.assertFalse(
                os.path.exists(expected_import_path),
                "Revision import '%d' was not removed." %
                revision)

            # Re-load base config contents.
            base = operating_system.read_file(
                strategy._base_config_path, strategy._codec)

            # Assert that the base config did not change.
            self.assertEqual(expected_contents_seq[revision - 1], base)

        # Test rollback all.
        ####################

        # Apply a sequence of overrides.
        for override in config_overrides_seq:
            strategy.apply_next(override)

        num_revisions = strategy.count_revisions()

        # Check that we have an expected number of revisions.
        self.assertEqual(len(config_overrides_seq), num_revisions)

        # Rollback all revisions at once.
        strategy.remove_last(num_revisions + 1)

        # Check that there are no revisions.
        self.assertEqual(0, strategy.count_revisions())

        # Check that all imports were removed.
        for revision, _ in reversed(
                [e for e in enumerate(config_overrides_seq, 1)]):
            expected_backup_path = build_revision_path(revision)
            self.assertFalse(
                os.path.exists(expected_backup_path),
                "Revision import '%d' was not removed." % revision)

        # Re-load base config contents.
        base = operating_system.read_file(
            strategy._base_config_path, strategy._codec)

        # Assert that the base config did not change.
        self.assertEqual(expected_contents_seq[0], base)

    def test_get_value(self):
        revision_dir = self._create_temp_dir()
        self._assert_get_value(RollingOverrideStrategy(revision_dir))
        self._assert_get_value(ImportOverrideStrategy(revision_dir, 'ext'))

    def _assert_get_value(self, override_strategy):
        base_config_contents = {'Section_1': {'name': 'pi',
                                              'is_number': 'True',
                                              'value': '3.1415'}
                                }

        config_overrides_v1 = {'Section_1': {'name': 'sqrt(2)',
                                             'value': '1.4142'}
                               }

        config_overrides_v2 = {'Section_1': {'name': 'e',
                                             'value': '2.7183'},
                               'Section_2': {'foo': 'bar'}
                               }

        codec = IniCodec()
        current_user = getpass.getuser()

        with tempfile.NamedTemporaryFile() as base_config:

            # Write initial config contents.
            operating_system.write_file(
                base_config.name, base_config_contents, codec)

            manager = ConfigurationManager(
                base_config.name, current_user, current_user, codec,
                requires_root=False)

            manager.set_override_strategy(override_strategy, 2)

            # Test default value.
            self.assertEqual(None, manager.get_value('Section_2'))
            self.assertEqual('foo', manager.get_value('Section_2', 'foo'))

            # Test value before applying overrides.
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])

            # Test value after applying overrides.
            manager.apply_override(config_overrides_v1)
            self.assertEqual('sqrt(2)', manager.get_value('Section_1')['name'])
            self.assertEqual('1.4142', manager.get_value('Section_1')['value'])
            manager.apply_override(config_overrides_v2)
            self.assertEqual('e', manager.get_value('Section_1')['name'])
            self.assertEqual('2.7183', manager.get_value('Section_1')['value'])
            self.assertEqual('bar', manager.get_value('Section_2')['foo'])

            # Test value after removing overrides.
            manager.remove_override()
            self.assertEqual('sqrt(2)', manager.get_value('Section_1')['name'])
            self.assertEqual('1.4142', manager.get_value('Section_1')['value'])
            manager.remove_override()
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])
            self.assertEqual(None, manager.get_value('Section_2'))

    def test_update_configuration(self):
        revision_dir = self._create_temp_dir()
        self._assert_update_configuration(
            RollingOverrideStrategy(revision_dir))
        self._assert_update_configuration(
            ImportOverrideStrategy(revision_dir, 'ext'))

    def _assert_update_configuration(self, override_strategy):
        base_config_contents = {'Section_1': {'name': 'pi',
                                              'is_number': 'True',
                                              'value': '3.1415'}
                                }

        config_overrides_v1 = {'Section_1': {'name': 'sqrt(2)',
                                             'value': '1.4142'}
                               }

        config_overrides_v2 = {'Section_1': {'name': 'e',
                                             'value': '2.7183'},
                               'Section_2': {'foo': 'bar'}
                               }

        codec = IniCodec()
        current_user = getpass.getuser()

        with tempfile.NamedTemporaryFile() as base_config:

            # Write initial config contents.
            operating_system.write_file(
                base_config.name, base_config_contents, codec)

            manager = ConfigurationManager(
                base_config.name, current_user, current_user, codec,
                requires_root=False)

            manager.update_configuration({'System': {'name': 'c',
                                                     'is_number': 'True',
                                                     'value': 'N/A'}})

            manager.set_override_strategy(override_strategy, 2)

            # Test value before applying overrides.
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])
            self.assertEqual('N/A', manager.get_value('System')['value'])
            self.assertEqual(0, manager.current_revision)

            manager.update_configuration({'System': {'value': '300000000'}})
            self.assertEqual('300000000', manager.get_value('System')['value'])
            self.assertEqual(0, manager.current_revision)

            # Test value after applying overrides.
            manager.apply_override(config_overrides_v1)
            self.assertEqual('sqrt(2)', manager.get_value('Section_1')['name'])
            self.assertEqual('1.4142', manager.get_value('Section_1')['value'])
            self.assertEqual('300000000', manager.get_value('System')['value'])
            self.assertEqual(1, manager.current_revision)

            manager.update_configuration({'System': {'value': '299792458'}})

            manager.apply_override(config_overrides_v2)
            self.assertEqual('e', manager.get_value('Section_1')['name'])
            self.assertEqual('2.7183', manager.get_value('Section_1')['value'])
            self.assertEqual('bar', manager.get_value('Section_2')['foo'])
            self.assertEqual('299792458', manager.get_value('System')['value'])
            self.assertEqual(2, manager.current_revision)

            # Test value after removing overrides.
            manager.remove_override()
            self.assertEqual('sqrt(2)', manager.get_value('Section_1')['name'])
            self.assertEqual('1.4142', manager.get_value('Section_1')['value'])
            self.assertEqual(1, manager.current_revision)

            manager.update_configuration({'System': {'value': '299792458'}})

            manager.remove_override()
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])
            self.assertEqual(None, manager.get_value('Section_2'))
            self.assertEqual(0, manager.current_revision)

            manager.update_configuration({'System': {'value': 'N/A'}})
            self.assertEqual('N/A', manager.get_value('System')['value'])
            self.assertEqual(0, manager.current_revision)
