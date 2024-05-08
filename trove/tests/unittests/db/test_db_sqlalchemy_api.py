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
