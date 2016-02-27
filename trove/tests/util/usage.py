# Copyright (c) 2013 Rackspace Hosting
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

from collections import defaultdict

from oslo_log import log as logging
import proboscis.asserts as asserts
from proboscis.dependencies import SkipTest

from trove.common import utils
from trove.tests.config import CONFIG

LOG = logging.getLogger(__name__)
MESSAGE_QUEUE = defaultdict(list)


def create_usage_verifier():
    return utils.import_object(CONFIG.usage_endpoint)


class UsageVerifier(object):

    def clear_events(self):
        """Hook that is called to allow endpoints to clean up."""
        pass

    def check_message(self, resource_id, event_type, **attrs):
        messages = utils.poll_until(lambda: self.get_messages(resource_id),
                                    lambda x: len(x) > 0, time_out=30)
        found = None
        for message in messages:
            if message['event_type'] == event_type:
                found = message
        asserts.assert_is_not_none(found,
                                   "No message type %s for resource %s" %
                                   (event_type, resource_id))
        with asserts.Check() as check:
            for key, value in attrs.iteritems():
                check.equal(found[key], value)

    def get_messages(self, resource_id, expected_messages=None):
        global MESSAGE_QUEUE
        msgs = MESSAGE_QUEUE.get(resource_id, [])
        if expected_messages is not None:
            asserts.assert_equal(len(msgs), expected_messages)
        return msgs


class FakeVerifier(object):
    """This is the default handler in fake mode, it is basically a no-op."""

    def clear_events(self):
        pass

    def check_message(self, *args, **kwargs):
        raise SkipTest("Notifications not available")

    def get_messages(self, *args, **kwargs):
        pass


def notify(event_type, payload):
    """Simple test notify function which saves the messages to global list."""
    payload['event_type'] = event_type
    if 'instance_id' in payload and 'server_type' not in payload:
        LOG.debug('Received Usage Notification: %s' % event_type)
        resource_id = payload['instance_id']
        global MESSAGE_QUEUE
        MESSAGE_QUEUE[resource_id].append(payload)
        LOG.debug('Message Queue for %(id)s now has %(msg_count)d messages' %
                  {'id': resource_id,
                   'msg_count': len(MESSAGE_QUEUE[resource_id])})
