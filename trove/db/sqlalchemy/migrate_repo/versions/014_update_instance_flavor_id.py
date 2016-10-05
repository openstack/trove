# Copyright 2012 OpenStack Foundation
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

from sqlalchemy.schema import MetaData

from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import Table


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    # pgsql <= 8.3 was lax about char->other casting but this was tightened up
    # in 8.4+. We now have to specify the USING clause for the cast to succeed.
    # NB: The generated sqlalchemy query doesn't support this, so this override
    # is needed.
    if migrate_engine.name == 'postgresql':
        migrate_engine.execute('ALTER TABLE instances ALTER COLUMN flavor_id '
                               'TYPE INTEGER USING flavor_id::integer')
    else:
        instances = Table('instances', meta, autoload=True)
        # modify column
        instances.c.flavor_id.alter(type=Integer())
