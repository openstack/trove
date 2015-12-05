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
from mock import call
from mock import DEFAULT
from mock import MagicMock
from mock import Mock
from mock import patch
import os
import tempfile
from trove.common.stream_codecs import IniCodec
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.common.configuration import OneFileOverrideStrategy
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
        sample_strategy = MagicMock()
        sample_strategy.configure = Mock()
        sample_strategy.parse_updates = Mock(return_value={})

        manager = ConfigurationManager(
            sample_path, sample_owner, sample_group, sample_codec,
            requires_root=sample_requires_root,
            override_strategy=sample_strategy)

        manager.parse_configuration()
        read_file.assert_called_with(sample_path, codec=sample_codec,
                                     as_root=sample_requires_root)

        with patch.object(manager, 'parse_configuration',
                          return_value={'key1': 'v1', 'key2': 'v2'}):
            self.assertEqual('v1', manager.get_value('key1'))
            self.assertIsNone(manager.get_value('key3'))

        sample_contents = Mock()
        manager.save_configuration(sample_contents)
        write_file.assert_called_with(
            sample_path, sample_contents, as_root=sample_requires_root)

        chown.assert_called_with(sample_path, sample_owner, sample_group,
                                 as_root=sample_requires_root)
        chmod.assert_called_with(
            sample_path, FileMode.ADD_READ_ALL, as_root=sample_requires_root)

        sample_data = {}
        manager.apply_system_override(sample_data)
        manager.apply_user_override(sample_data)
        manager.apply_system_override(sample_data, change_id='sys1')
        manager.apply_user_override(sample_data, change_id='usr1')
        sample_strategy.apply.has_calls([
            call(manager.SYSTEM_GROUP, manager.DEFAULT_CHANGE_ID, sample_data),
            call(manager.USER_GROUP, manager.DEFAULT_CHANGE_ID, sample_data),
            call(manager.SYSTEM_GROUP, 'sys1', sample_data),
            call(manager.USER_GROUP, 'usr1', sample_data)
        ])


class TestConfigurationOverrideStrategy(trove_testtools.TestCase):

    def setUp(self):
        trove_testtools.TestCase.setUp(self)
        self._temp_files_paths = []
        self.chmod_patch = patch.object(
            operating_system, 'chmod',
            MagicMock(return_value=None))
        self.chmod_patch_mock = self.chmod_patch.start()
        self.addCleanup(self.chmod_patch.stop)

    def tearDown(self):
        trove_testtools.TestCase.tearDown(self)

        # Remove temporary files in the LIFO order.
        while self._temp_files_paths:
            try:
                os.remove(self._temp_files_paths.pop())
            except Exception:
                pass  # Do not fail in cleanup.

    def _create_temp_dir(self):
        path = tempfile.mkdtemp()
        self._temp_files_paths.append(path)
        return path

    def test_import_override_strategy(self):

        # Data structures representing overrides.
        # ('change id', 'values', 'expected import index',
        # 'expected final import data')

        # Distinct IDs within each group mean that there is one file for each
        # override.
        user_overrides_v1 = ('id1',
                             {'Section_1': {'name': 'sqrt(2)',
                                            'value': '1.4142'}},
                             1,
                             {'Section_1': {'name': 'sqrt(2)',
                                            'value': '1.4142'}}
                             )

        user_overrides_v2 = ('id2',
                             {'Section_1': {'is_number': 'False'}},
                             2,
                             {'Section_1': {'is_number': 'False'}}
                             )

        system_overrides_v1 = ('id1',
                               {'Section_1': {'name': 'e',
                                              'value': '2.7183'}},
                               1,
                               {'Section_1': {'name': 'e',
                                              'value': '2.7183'}}
                               )

        system_overrides_v2 = ('id2',
                               {'Section_2': {'is_number': 'True'}},
                               2,
                               {'Section_2': {'is_number': 'True'}}
                               )

        self._test_import_override_strategy(
            [system_overrides_v1, system_overrides_v2],
            [user_overrides_v1, user_overrides_v2], True)

        # Same IDs within a group mean that the overrides get written into a
        # single file.
        user_overrides_v1 = ('id1',
                             {'Section_1': {'name': 'sqrt(2)',
                                            'value': '1.4142'}},
                             1,
                             {'Section_1': {'name': 'sqrt(2)',
                                            'is_number': 'False',
                                            'value': '1.4142'}}
                             )

        user_overrides_v2 = ('id1',
                             {'Section_1': {'is_number': 'False'}},
                             1,
                             {'Section_1': {'name': 'sqrt(2)',
                                            'is_number': 'False',
                                            'value': '1.4142'}}
                             )

        system_overrides_v1 = ('id1',
                               {'Section_1': {'name': 'e',
                                              'value': '2.7183'}},
                               1,
                               {'Section_1': {'name': 'e',
                                              'value': '2.7183'},
                                'Section_2': {'is_number': 'True'}}
                               )

        system_overrides_v2 = ('id1',
                               {'Section_2': {'is_number': 'True'}},
                               1,
                               {'Section_1': {'name': 'e',
                                              'value': '2.7183'},
                                'Section_2': {'is_number': 'True'}}
                               )

        self._test_import_override_strategy(
            [system_overrides_v1, system_overrides_v2],
            [user_overrides_v1, user_overrides_v2], False)

    @patch.multiple(operating_system, chmod=Mock(), chown=Mock())
    def _test_import_override_strategy(
            self, system_overrides, user_overrides, test_multi_rev):
        base_config_contents = {'Section_1': {'name': 'pi',
                                              'is_number': 'True',
                                              'value': '3.1415'}
                                }

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
                strategy, system_overrides, user_overrides, test_multi_rev)

    def _assert_import_override_strategy(
            self, strategy, system_overrides, user_overrides, test_multi_rev):

        def import_path_builder(
                root, group_name, change_id, file_index, file_ext):
            return os.path.join(
                root, '%s-%03d-%s.%s'
                % (group_name, file_index, change_id, file_ext))

        # Apply and remove overrides sequentially.
        ##########################################

        # Apply the overrides and verify the files as they are created.
        self._apply_import_overrides(
            strategy, 'system', system_overrides, import_path_builder)
        self._apply_import_overrides(
            strategy, 'user', user_overrides, import_path_builder)

        # Verify the files again after applying all overrides.
        self._assert_import_overrides(
            strategy, 'system', system_overrides, import_path_builder)
        self._assert_import_overrides(
            strategy, 'user', user_overrides, import_path_builder)

        # Remove the overrides and verify the files are gone.
        self._remove_import_overrides(
            strategy, 'user', user_overrides, import_path_builder)
        self._remove_import_overrides(
            strategy, 'system', user_overrides, import_path_builder)

        # Remove a whole group.
        ##########################################

        # Apply overrides first.
        self._apply_import_overrides(
            strategy, 'system', system_overrides, import_path_builder)
        self._apply_import_overrides(
            strategy, 'user', user_overrides, import_path_builder)

        # Remove all user overrides and verify the files are gone.
        self._remove_import_overrides(
            strategy, 'user', None, import_path_builder)

        # Assert that the system files are still there intact.
        self._assert_import_overrides(
            strategy, 'system', system_overrides, import_path_builder)

        # Remove all system overrides and verify the files are gone.
        self._remove_import_overrides(
            strategy, 'system', None, import_path_builder)

        if test_multi_rev:

            # Remove at the end (only if we have multiple revision files).
            ##########################################

            # Apply overrides first.
            self._apply_import_overrides(
                strategy, 'system', system_overrides, import_path_builder)
            self._apply_import_overrides(
                strategy, 'user', user_overrides, import_path_builder)

            # Remove the last user and system overrides.
            self._remove_import_overrides(
                strategy, 'user', [user_overrides[-1]], import_path_builder)
            self._remove_import_overrides(
                strategy, 'system', [system_overrides[-1]],
                import_path_builder)

            # Assert that the first overrides are still there intact.
            self._assert_import_overrides(
                strategy, 'user', [user_overrides[0]], import_path_builder)
            self._assert_import_overrides(
                strategy, 'system', [system_overrides[0]], import_path_builder)

            # Re-apply all overrides.
            self._apply_import_overrides(
                strategy, 'system', system_overrides, import_path_builder)
            self._apply_import_overrides(
                strategy, 'user', user_overrides, import_path_builder)

            # This should overwrite the existing files and resume counting from
            # their indices.
            self._assert_import_overrides(
                strategy, 'user', user_overrides, import_path_builder)
            self._assert_import_overrides(
                strategy, 'system', system_overrides, import_path_builder)

    def _apply_import_overrides(
            self, strategy, group_name, overrides, path_builder):
        # Apply the overrides and immediately check the file and its contents.
        for change_id, contents, index, _ in overrides:
            strategy.apply(group_name, change_id, contents)
            expected_path = path_builder(
                strategy._revision_dir, group_name, change_id, index,
                strategy._revision_ext)
            self._assert_file_exists(expected_path, True)

    def _remove_import_overrides(
            self, strategy, group_name, overrides, path_builder):
        if overrides:
            # Remove the overrides and immediately check the file was removed.
            for change_id, _, index, _ in overrides:
                strategy.remove(group_name, change_id)
                expected_path = path_builder(
                    strategy._revision_dir, group_name, change_id, index,
                    strategy._revision_ext)
                self._assert_file_exists(expected_path, False)
        else:
            # Remove the entire group.
            strategy.remove(group_name)
            found = operating_system.list_files_in_directory(
                strategy._revision_dir, pattern='^%s-.+$' % group_name)
            self.assertEqual(set(), found, "Some import files from group '%s' "
                             "were not removed." % group_name)

    def _assert_import_overrides(
            self, strategy, group_name, overrides, path_builder):
        # Check all override files and their contents,
        for change_id, _, index, expected in overrides:
            expected_path = path_builder(
                strategy._revision_dir, group_name, change_id, index,
                strategy._revision_ext)
            self._assert_file_exists(expected_path, True)
            # Assert that the file contents.
            imported = operating_system.read_file(
                expected_path, codec=strategy._codec)
            self.assertEqual(expected, imported)

    def _assert_file_exists(self, file_path, exists):
        if exists:
            self.assertTrue(os.path.exists(file_path),
                            "Revision import '%s' does not exist."
                            % file_path)
        else:
            self.assertFalse(os.path.exists(file_path),
                             "Revision import '%s' was not removed."
                             % file_path)

    def test_get_value(self):
        revision_dir = self._create_temp_dir()
        self._assert_get_value(ImportOverrideStrategy(revision_dir, 'ext'))
        self._assert_get_value(OneFileOverrideStrategy(revision_dir))

    @patch.multiple(operating_system, chmod=Mock(), chown=Mock())
    def _assert_get_value(self, override_strategy):
        base_config_contents = {'Section_1': {'name': 'pi',
                                              'is_number': 'True',
                                              'value': '3.1415'}
                                }

        config_overrides_v1a = {'Section_1': {'name': 'sqrt(2)',
                                              'value': '1.4142'}
                                }

        config_overrides_v2 = {'Section_1': {'name': 'e',
                                             'value': '2.7183'},
                               'Section_2': {'foo': 'bar'}
                               }

        config_overrides_v1b = {'Section_1': {'name': 'sqrt(4)',
                                              'value': '2.0'}
                                }

        codec = IniCodec()
        current_user = getpass.getuser()

        with tempfile.NamedTemporaryFile() as base_config:

            # Write initial config contents.
            operating_system.write_file(
                base_config.name, base_config_contents, codec)

            manager = ConfigurationManager(
                base_config.name, current_user, current_user, codec,
                requires_root=False, override_strategy=override_strategy)

            # Test default value.
            self.assertIsNone(manager.get_value('Section_2'))
            self.assertEqual('foo', manager.get_value('Section_2', 'foo'))

            # Test value before applying overrides.
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])

            # Test value after applying overrides.
            manager.apply_user_override(config_overrides_v1a, change_id='id1')
            self.assertEqual('sqrt(2)', manager.get_value('Section_1')['name'])
            self.assertEqual('1.4142', manager.get_value('Section_1')['value'])
            manager.apply_user_override(config_overrides_v2, change_id='id2')
            self.assertEqual('e', manager.get_value('Section_1')['name'])
            self.assertEqual('2.7183', manager.get_value('Section_1')['value'])
            self.assertEqual('bar', manager.get_value('Section_2')['foo'])

            # Editing change 'id1' become visible only after removing
            # change 'id2', which overrides 'id1'.
            manager.apply_user_override(config_overrides_v1b, change_id='id1')
            self.assertEqual('e', manager.get_value('Section_1')['name'])
            self.assertEqual('2.7183', manager.get_value('Section_1')['value'])

            # Test value after removing overrides.

            # The edited values from change 'id1' should be visible after
            # removing 'id2'.
            manager.remove_user_override(change_id='id2')
            self.assertEqual('sqrt(4)', manager.get_value('Section_1')['name'])
            self.assertEqual('2.0', manager.get_value('Section_1')['value'])

            # Back to the base.
            manager.remove_user_override(change_id='id1')
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])
            self.assertIsNone(manager.get_value('Section_2'))

            # Test system overrides.
            manager.apply_system_override(
                config_overrides_v1b, change_id='id1')
            self.assertEqual('sqrt(4)', manager.get_value('Section_1')['name'])
            self.assertEqual('2.0', manager.get_value('Section_1')['value'])

            # The system values should take precedence over the user
            # override.
            manager.apply_user_override(
                config_overrides_v1a, change_id='id1')
            self.assertEqual('sqrt(4)', manager.get_value('Section_1')['name'])
            self.assertEqual('2.0', manager.get_value('Section_1')['value'])

            # The user values should become visible only after removing the
            # system change.
            manager.remove_system_override(change_id='id1')
            self.assertEqual('sqrt(2)', manager.get_value('Section_1')['name'])
            self.assertEqual('1.4142', manager.get_value('Section_1')['value'])

            # Back to the base.
            manager.remove_user_override(change_id='id1')
            self.assertEqual('pi', manager.get_value('Section_1')['name'])
            self.assertEqual('3.1415', manager.get_value('Section_1')['value'])
            self.assertIsNone(manager.get_value('Section_2'))
