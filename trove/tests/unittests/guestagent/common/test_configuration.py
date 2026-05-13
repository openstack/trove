#    Copyright 2026 PS Cloud Services
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import testtools
from trove.guestagent.common.configuration import IndexOverrideStrategy
from unittest import mock


class IndexOverrideStrategyTest(testtools.TestCase):
    def setUp(self):
        super().setUp()

        self.revision_dir = "/etc/test/conf.d"
        self.revision_ext = "conf"
        self.index_file = "/etc/test/conf.d/index.conf"

        self.strategy = IndexOverrideStrategy(
            self.revision_dir,
            self.revision_ext,
        )

        self.strategy._owner = "test-user"
        self.strategy._group = "test-group"
        self.strategy._codec = mock.Mock()
        self.strategy._requires_root = False

    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chmod")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chown")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.write_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.exists")
    @mock.patch.object(
        IndexOverrideStrategy.__bases__[0], "configure")
    def test_configure_creates_index_file(
            self, configure, exists, write_file, chown, chmod):

        exists.return_value = False

        self.strategy.configure(
            "/etc/test/test.conf",
            "test-user",
            "test-group",
            mock.Mock(),
            False,
        )

        configure.assert_called_once_with(
            "/etc/test/test.conf",
            "test-user",
            "test-group",
            mock.ANY,
            False,
        )

        exists.assert_called_once_with(
            self.index_file,
            as_root=False,
        )

        write_file.assert_called_once_with(
            self.index_file,
            "",
            as_root=False,
        )

        chown.assert_called_once_with(
            self.index_file,
            "test-user",
            "test-group",
            as_root=False,
        )

        chmod.assert_called_once()

    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chmod")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chown")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.write_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.exists")
    @mock.patch.object(
        IndexOverrideStrategy.__bases__[0], "configure")
    def test_configure_does_not_recreate_existing_index(
            self, configure, exists, write_file, chown, chmod):

        exists.return_value = True

        self.strategy.configure(
            "/etc/test/test.conf",
            "test-user",
            "test-group",
            mock.Mock(),
            False,
        )

        write_file.assert_not_called()
        chown.assert_not_called()
        chmod.assert_not_called()

    @mock.patch.object(IndexOverrideStrategy, "_add_to_index")
    @mock.patch.object(IndexOverrideStrategy, "_get_last_file_index")
    @mock.patch.object(IndexOverrideStrategy, "_find_revision_file")
    @mock.patch.object(IndexOverrideStrategy, "_initialize_import_directory")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chmod")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chown")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.write_file")
    def test_apply_creates_revision_and_adds_to_index(
            self, write_file, chown, chmod, initialize,
            find_revision_file, get_last_file_index, add_to_index):

        find_revision_file.return_value = None
        get_last_file_index.return_value = 0

        options = {"foo": "bar"}

        revision_file = ("/etc/test/conf.d/group-001-change-id.conf")

        self.strategy.apply("group", "change-id", options)
        initialize.assert_called_once_with()
        get_last_file_index.assert_called_once_with("group")

        write_file.assert_called_once_with(
            revision_file,
            options,
            codec=self.strategy._codec,
            as_root=False,
        )

        chown.assert_called_once_with(
            revision_file,
            "test-user",
            "test-group",
            as_root=False,
        )

        chmod.assert_called_once()

        add_to_index.assert_called_once_with(revision_file)

    @mock.patch.object(IndexOverrideStrategy, "_add_to_index")
    @mock.patch.object(IndexOverrideStrategy, "_find_revision_file")
    @mock.patch.object(IndexOverrideStrategy, "_initialize_import_directory")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chmod")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.chown")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.write_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.read_file")
    def test_apply_updates_existing_revision(
            self, read_file, write_file, chown, chmod, initialize,
            find_revision_file, add_to_index):

        revision_file = (
            "/etc/test/conf.d/group-001-change-id.conf"
        )

        find_revision_file.return_value = revision_file
        read_file.return_value = {"existing": "value", "remove": "value"}
        options = {"new": "value", "remove": None}

        self.strategy.apply("group", "change-id", options)

        write_file.assert_called_once_with(
            revision_file,
            {
                "existing": "value",
                "new": "value",
            },
            codec=self.strategy._codec,
            as_root=False,
        )

        add_to_index.assert_not_called()

    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.read_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.exists")
    def test_read_index(self, exists, read_file):

        exists.return_value = True
        read_file.return_value = (
            "include /etc/test/conf.d/a.conf\n"
            "\n"
            "  include /etc/test/conf.d/b.conf  \n"
        )

        result = self.strategy._read_index()

        self.assertEqual([
            "include /etc/test/conf.d/a.conf",
            "include /etc/test/conf.d/b.conf",
        ], result)

    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.read_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.exists")
    def test_read_index_returns_empty_list_when_index_does_not_exist(
            self, exists, read_file):
        exists.return_value = False
        result = self.strategy._read_index()
        self.assertEqual([], result)
        read_file.assert_not_called()

    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.write_file")
    def test_write_index(self, write_file):
        self.strategy._write_index([
            "include /etc/test/conf.d/a.conf",
            "include /etc/test/conf.d/b.conf",
        ])

        write_file.assert_called_once_with(
            self.index_file,
            "include /etc/test/conf.d/a.conf\n"
            "include /etc/test/conf.d/b.conf\n",
            as_root=False,
        )

    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.write_file")
    def test_write_empty_index(self, write_file):
        self.strategy._write_index([])
        write_file.assert_called_once_with(
            self.index_file,
            "",
            as_root=False,
        )

    @mock.patch.object(IndexOverrideStrategy, "_write_index")
    @mock.patch.object(IndexOverrideStrategy, "_read_index")
    def test_add_to_index(self, read_index, write_index):

        read_index.return_value = [
            "include /etc/test/conf.d/old.conf",
        ]

        self.strategy._add_to_index(
            "/etc/test/conf.d/new.conf"
        )

        write_index.assert_called_once_with([
            "include /etc/test/conf.d/old.conf",
            "include /etc/test/conf.d/new.conf",
        ])

    @mock.patch.object(IndexOverrideStrategy, "_write_index")
    @mock.patch.object(IndexOverrideStrategy, "_read_index")
    def test_add_to_index_does_not_duplicate_record(
            self, read_index, write_index):

        record = "include /etc/test/conf.d/file.conf"

        read_index.return_value = [record]

        self.strategy._add_to_index(
            "/etc/test/conf.d/file.conf"
        )

        write_index.assert_called_once_with([record])

    @mock.patch.object(IndexOverrideStrategy, "_write_index")
    @mock.patch.object(IndexOverrideStrategy, "_read_index")
    def test_remove_from_index(self, read_index, write_index):

        read_index.return_value = [
            "include /etc/test/conf.d/a.conf",
            "include /etc/test/conf.d/b.conf",
        ]
        self.strategy._remove_from_index("/etc/test/conf.d/a.conf")
        write_index.assert_called_once_with([
            "include /etc/test/conf.d/b.conf",
        ])

    @mock.patch.object(IndexOverrideStrategy, "_remove_from_index")
    @mock.patch.object(IndexOverrideStrategy, "_find_revision_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.remove")
    def test_remove_specific_revision(
            self, remove, find_revision_file, remove_from_index):

        revision_file = (
            "/etc/test/conf.d/group-001-change-id.conf"
        )
        find_revision_file.return_value = revision_file

        self.strategy.remove(
            "group",
            "change-id",
        )

        remove_from_index.assert_called_once_with(
            revision_file,
        )

        remove.assert_called_once_with(
            revision_file,
            force=True,
            as_root=False,
        )

    @mock.patch.object(IndexOverrideStrategy, "_remove_from_index")
    @mock.patch.object(IndexOverrideStrategy, "_find_revision_file")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.remove")
    def test_remove_specific_revision_does_nothing_if_not_found(
            self, remove, find_revision_file, remove_from_index):

        find_revision_file.return_value = None

        self.strategy.remove(
            "group",
            "change-id",
        )

        remove_from_index.assert_not_called()
        remove.assert_not_called()

    @mock.patch.object(IndexOverrideStrategy, "_remove_from_index")
    @mock.patch.object(IndexOverrideStrategy, "_collect_revision_files")
    @mock.patch(
        "trove.guestagent.common.configuration.operating_system.remove")
    def test_remove_all_group_revisions(
            self, remove, collect_revision_files, remove_from_index):

        revision_files = [
            "/etc/test/conf.d/group-001-first.conf",
            "/etc/test/conf.d/group-002-second.conf",
        ]
        collect_revision_files.return_value = revision_files

        self.strategy.remove("group")
        self.assertEqual(
            2,
            remove_from_index.call_count,
        )
        self.assertEqual(
            2,
            remove.call_count,
        )
        for path in revision_files:
            remove_from_index.assert_any_call(path)
            remove.assert_any_call(
                path,
                force=True,
                as_root=False,
            )
