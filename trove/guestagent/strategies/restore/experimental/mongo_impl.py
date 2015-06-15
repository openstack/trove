# Copyright (c) 2014 eBay Software Foundation
# Copyright 2015 Hewlett-Packard Development Company, L.P. and Tesora, Inc
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
#

from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mongodb import (
    service as mongo_service)
from trove.guestagent.strategies.restore import base

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
IP = netutils.get_my_ipv4()
LARGE_TIMEOUT = 1200
MONGODB_DBPATH = CONF.mongodb.mount_point
MONGO_DUMP_DIR = MONGODB_DBPATH + "/dump"


class MongoDump(base.RestoreRunner):
    __strategy_name__ = 'mongodump'
    base_restore_cmd = 'sudo tar xPf -'

    def __init__(self, *args, **kwargs):
        super(MongoDump, self).__init__(*args, **kwargs)
        self.app = mongo_service.MongoDBApp()

    def post_restore(self):
        """
        Restore from the directory that we untarred into
        """
        params = self.app.admin_cmd_auth_params()
        params.append(MONGO_DUMP_DIR)
        utils.execute_with_timeout('mongorestore', *params,
                                   timeout=LARGE_TIMEOUT)

        operating_system.remove(MONGO_DUMP_DIR, force=True, as_root=True)
