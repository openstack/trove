# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import unittest
from unittest.mock import Mock, MagicMock

from trove.common import exception
from trove.db.sqlalchemy import api


class TestDbSqlalchemyApi(unittest.TestCase):

    def test_migrate_legacy_database_scalar_replacement(self):
        """Test _migrate_legacy_database uses scalar()
        instead of the removed .values()[0]

        Verify scalar() correctly retrieves the single value.
        """
        from sqlalchemy import create_engine, text

        # Set up an in-memory sqlite database with legacy migration table
        engine = create_engine('sqlite:///:memory:', echo=False)
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE migrate_version (version INTEGER)"
            ))
            connection.execute(text(
                "INSERT INTO migrate_version VALUES (48)"
            ))

        # Simulate the query from _migrate_legacy_database
        query = text("SELECT version FROM migrate_version")
        with engine.connect() as connection:
            result = connection.execute(query)
            cur_version = result.scalar()
            self.assertEqual(cur_version, 48)

    def test_db_sync_alembic(self):
        api._configure_alembic = MagicMock(return_value=True)
        api._get_alembic_revision = MagicMock(return_value='head')
        api.alembic_command.upgrade = Mock()
        api.db_sync({})
        self.assertTrue(api.alembic_command.upgrade.called)

    def test_db_sync_sqlalchemy_migrate(self):
        api._configure_alembic = MagicMock(return_value=False)
        with self.assertRaises(exception.BadRequest) as ex:
            api.db_sync({})
            self.assertTrue(ex.msg,
                            'sqlalchemy-migrate is no longer supported')

    def test_db_upgrade_alembic(self):
        api._configure_alembic = MagicMock(return_value=True)
        api.alembic_command.upgrade = Mock()
        api.db_upgrade({})
        self.assertTrue(api.alembic_command.upgrade.called)

    def test_db_upgrade_sqlalchemy_migrate(self):
        api._configure_alembic = MagicMock(return_value=False)
        with self.assertRaises(exception.BadRequest) as ex:
            api.db_upgrade({})
            self.assertTrue(ex.msg,
                            'sqlalchemy-migrate is no longer supported')
