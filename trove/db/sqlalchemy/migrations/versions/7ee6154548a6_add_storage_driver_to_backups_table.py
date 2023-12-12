# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""add_storage_driver_to_backups_table

Revision ID: 7ee6154548a6
Revises: cee1bcba3541
Create Date: 2024-06-18 16:14:38.561592

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column
from sqlalchemy import Text, String
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = '7ee6154548a6'
down_revision: Union[str, None] = 'cee1bcba3541'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("backups", Column('storage_driver', Text(),
                                    nullable=True))
    backups_tables = table(
        "backups",
        column("storage_driver", String)
    )
    op.execute(
        backups_tables.update()
        .where(backups_tables.c.storage_driver.is_(None))
        .values({"storage_driver": "swift"})
    )


def downgrade() -> None:
    op.drop_column("backups", 'storage_driver')
