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

"""drop-migrate-version-table

Revision ID: cee1bcba3541
Revises: 5c68b4fb3cd1
Create Date: 2024-06-05 14:27:15.530991

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.engine import reflection


# revision identifiers, used by Alembic.
revision: str = 'cee1bcba3541'
down_revision: Union[str, None] = '5c68b4fb3cd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = reflection.Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    if 'migrate_version' in tables:
        op.drop_table('migrate_version')


def downgrade() -> None:
    pass
