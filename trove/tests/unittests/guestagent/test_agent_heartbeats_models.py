# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

from mock import patch
import uuid

from trove.common import exception
from trove.guestagent.models import AgentHeartBeat
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class AgentHeartBeatTest(trove_testtools.TestCase):

    def setUp(self):
        super(AgentHeartBeatTest, self).setUp()
        util.init_db()

    def tearDown(self):
        super(AgentHeartBeatTest, self).tearDown()

    def test_create(self):
        """
        Test the creation of a new agent heartbeat record
        """
        instance_id = str(uuid.uuid4())
        heartbeat = AgentHeartBeat.create(
            instance_id=instance_id)
        self.assertIsNotNone(heartbeat)

        self.assertIsNotNone(heartbeat.id)
        self.assertIsNotNone(heartbeat.instance_id)
        self.assertEqual(instance_id,
                         heartbeat.instance_id)
        self.assertIsNotNone(heartbeat.updated_at)
        self.assertIsNone(heartbeat.guest_agent_version)

    def test_create_with_version(self):
        """
        Test the creation of a new agent heartbeat record w/ guest version
        """
        instance_id = str(uuid.uuid4())
        heartbeat = AgentHeartBeat.create(
            instance_id=instance_id,
            guest_agent_version="1.2.3")
        self.assertIsNotNone(heartbeat)

        self.assertIsNotNone(heartbeat.id)
        self.assertIsNotNone(heartbeat.instance_id)
        self.assertEqual(instance_id,
                         heartbeat.instance_id)
        self.assertIsNotNone(heartbeat.updated_at)
        self.assertIsNotNone(heartbeat.guest_agent_version)
        self.assertEqual("1.2.3", heartbeat.guest_agent_version)

    def test_find_by_instance_id(self):
        """
        Test to retrieve a guest agents by it's id
        """
        # create a unique record
        instance_id = str(uuid.uuid4())
        heartbeat = AgentHeartBeat.create(
            instance_id=instance_id, guest_agent_version="1.2.3")
        self.assertIsNotNone(heartbeat)
        self.assertIsNotNone(heartbeat.id)
        self.assertIsNotNone(heartbeat.instance_id)
        self.assertEqual(instance_id, heartbeat.instance_id)
        self.assertIsNotNone(heartbeat.updated_at)
        self.assertIsNotNone(heartbeat.guest_agent_version)
        self.assertEqual("1.2.3", heartbeat.guest_agent_version)

        # retrieve the record
        heartbeat_found = AgentHeartBeat.find_by_instance_id(
            instance_id=instance_id)
        self.assertIsNotNone(heartbeat_found)
        self.assertEqual(heartbeat.id, heartbeat_found.id)
        self.assertEqual(heartbeat.instance_id, heartbeat_found.instance_id)
        self.assertEqual(heartbeat.updated_at, heartbeat_found.updated_at)
        self.assertEqual(heartbeat.guest_agent_version,
                         heartbeat_found.guest_agent_version)

    def test_find_by_instance_id_none(self):
        """
        Test to retrieve a guest agents when id is None
        """
        heartbeat_found = None
        exception_raised = False
        try:
            heartbeat_found = AgentHeartBeat.find_by_instance_id(
                instance_id=None)
        except exception.ModelNotFoundError:
            exception_raised = True

        self.assertIsNone(heartbeat_found)
        self.assertTrue(exception_raised)

    @patch('trove.guestagent.models.LOG')
    def test_find_by_instance_id_not_found(self, mock_logging):
        """
        Test to retrieve a guest agents when id is not found
        """
        instance_id = str(uuid.uuid4())
        heartbeat_found = None
        exception_raised = False
        try:
            heartbeat_found = AgentHeartBeat.find_by_instance_id(
                instance_id=instance_id)
        except exception.ModelNotFoundError:
            exception_raised = True

        self.assertIsNone(heartbeat_found)
        self.assertTrue(exception_raised)

    def test_find_all_by_version(self):
        """
        Test to retrieve all guest agents with a particular version
        """
        # create some unique records with the same version
        version = str(uuid.uuid4())

        for x in xrange(5):
            instance_id = str(uuid.uuid4())
            heartbeat = AgentHeartBeat.create(
                instance_id=instance_id,
                guest_agent_version=version,
                deleted=0)
            self.assertIsNotNone(heartbeat)

        # get all guests by version
        heartbeats = AgentHeartBeat.find_all_by_version(version)
        self.assertIsNotNone(heartbeats)
        self.assertEqual(5, heartbeats.count())

    def test_find_all_by_version_none(self):
        """
        Test to retrieve all guest agents with a None version
        """
        heartbeats = None
        exception_raised = False
        try:
            heartbeats = AgentHeartBeat.find_all_by_version(None)
        except exception.ModelNotFoundError:
            exception_raised = True

        self.assertIsNone(heartbeats)
        self.assertTrue(exception_raised)

    def test_find_all_by_version_not_found(self):
        """
        Test to retrieve all guest agents with a non-existing version
        """
        version = str(uuid.uuid4())
        exception_raised = False
        heartbeats = None
        try:
            heartbeats = AgentHeartBeat.find_all_by_version(version)
        except exception.ModelNotFoundError:
            exception_raised = True

        self.assertIsNone(heartbeats)
        self.assertTrue(exception_raised)

    def test_update_heartbeat(self):
        """
        Test to show the upgrade scenario that will be used by conductor
        """
        # create a unique record
        instance_id = str(uuid.uuid4())
        heartbeat = AgentHeartBeat.create(
            instance_id=instance_id, guest_agent_version="1.2.3")
        self.assertIsNotNone(heartbeat)
        self.assertIsNotNone(heartbeat.id)
        self.assertIsNotNone(heartbeat.instance_id)
        self.assertEqual(instance_id, heartbeat.instance_id)
        self.assertIsNotNone(heartbeat.updated_at)
        self.assertIsNotNone(heartbeat.guest_agent_version)
        self.assertEqual("1.2.3", heartbeat.guest_agent_version)

        # retrieve the record
        heartbeat_found = AgentHeartBeat.find_by_instance_id(
            instance_id=instance_id)
        self.assertIsNotNone(heartbeat_found)
        self.assertEqual(heartbeat.id, heartbeat_found.id)
        self.assertEqual(heartbeat.instance_id, heartbeat_found.instance_id)
        self.assertEqual(heartbeat.updated_at, heartbeat_found.updated_at)
        self.assertEqual(heartbeat.guest_agent_version,
                         heartbeat_found.guest_agent_version)

        # update
        AgentHeartBeat().update(id=heartbeat_found.id,
                                instance_id=instance_id,
                                guest_agent_version="1.2.3")

        # retrieve the record
        updated_heartbeat = AgentHeartBeat.find_by_instance_id(
            instance_id=instance_id)
        self.assertIsNotNone(updated_heartbeat)
        self.assertEqual(heartbeat.id, updated_heartbeat.id)
        self.assertEqual(heartbeat.instance_id, updated_heartbeat.instance_id)
        self.assertEqual(heartbeat.guest_agent_version,
                         updated_heartbeat.guest_agent_version)

        self.assertEqual(heartbeat.updated_at, updated_heartbeat.updated_at)
