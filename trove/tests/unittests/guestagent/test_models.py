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

from datetime import datetime

from mock import Mock, MagicMock, patch

from trove.common import timeutils
from trove.common import utils
from trove.db import models as dbmodels
from trove.db.sqlalchemy import api as dbapi
from trove.guestagent import models
from trove.tests.unittests import trove_testtools


class AgentHeartBeatTest(trove_testtools.TestCase):
    def setUp(self):
        super(AgentHeartBeatTest, self).setUp()
        self.origin_get_db_api = dbmodels.get_db_api
        self.origin_utcnow = timeutils.utcnow
        self.origin_db_api_save = dbapi.save
        self.origin_is_valid = dbmodels.DatabaseModelBase.is_valid
        self.origin_generate_uuid = utils.generate_uuid

    def tearDown(self):
        super(AgentHeartBeatTest, self).tearDown()
        dbmodels.get_db_api = self.origin_get_db_api
        timeutils.utcnow = self.origin_utcnow
        dbapi.save = self.origin_db_api_save
        dbmodels.DatabaseModelBase.is_valid = self.origin_is_valid
        utils.generate_uuid = self.origin_generate_uuid

    def test_create(self):
        utils.generate_uuid = Mock()
        dbapi.save = MagicMock(
            return_value=dbmodels.DatabaseModelBase)
        dbmodels.DatabaseModelBase.is_valid = Mock(return_value=True)
        models.AgentHeartBeat.create()
        self.assertEqual(1, utils.generate_uuid.call_count)
        self.assertEqual(3,
                         dbmodels.DatabaseModelBase.is_valid.call_count)

    @patch('trove.db.models.DatabaseModelBase')
    def test_save(self, dmb_mock):
        timeutils.utcnow = Mock()
        dbmodels.get_db_api = MagicMock(
            return_value=dbmodels.DatabaseModelBase)
        dbapi.save = Mock()
        dbmodels.DatabaseModelBase.is_valid = Mock(return_value=True)
        self.heartBeat = models.AgentHeartBeat()
        self.heartBeat.save()
        self.assertEqual(1, timeutils.utcnow.call_count)

    def test_is_active(self):
        models.AGENT_HEARTBEAT = 10000000000
        mock = models.AgentHeartBeat()
        models.AgentHeartBeat.__setitem__(mock, 'updated_at', datetime.now())
        self.assertTrue(models.AgentHeartBeat.is_active(mock))
