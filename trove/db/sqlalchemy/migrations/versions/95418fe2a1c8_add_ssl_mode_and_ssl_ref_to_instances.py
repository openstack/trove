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

"""add ssl_mode and ssl_ref to instances

Revision ID: 95418fe2a1c8
Revises: f90016d7baf8
Create Date: 2026-02-20 17:23:54.492132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import String, Text


# revision identifiers, used by Alembic.
revision: str = '95418fe2a1c8'
down_revision: Union[str, None] = 'f90016d7baf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'instances',
        sa.Column(
            'ssl_mode',
            String(16),
            nullable=True
        )
    )
    op.add_column(
        'instances',
        sa.Column(
            'ssl_ref',
            Text(),
            nullable=True
        )
    )


def downgrade() -> None:
    op.drop_column('instances', 'ssl_mode')
    op.drop_column('instances', 'ssl_ref')
