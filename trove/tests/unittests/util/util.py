#    Copyright 2012 OpenStack Foundation
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

import threading

from trove.common import cfg
from trove.db import get_db_api
from trove.db.sqlalchemy import session

CONF = cfg.CONF
DB_SETUP = None
LOCK = threading.Lock()


def init_db():
    with LOCK:
        global DB_SETUP
        if not DB_SETUP:
            db_api = get_db_api()
            db_api.db_sync(CONF)
            session.configure_db(CONF)
            DB_SETUP = True
