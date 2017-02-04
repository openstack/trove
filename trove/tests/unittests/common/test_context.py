# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
import mock
from mock import Mock

from testtools.matchers import Equals, Is
from trove.common import context
from trove.common.notification import DBaaSInstanceCreate
from trove.tests.unittests import trove_testtools


class TestTroveContext(trove_testtools.TestCase):
    def test_create_with_extended_args(self):
        expected_service_catalog = {'key': 'value'}
        ctx = context.TroveContext(user="test_user_id",
                                   request_id="test_req_id",
                                   limit="500",
                                   marker="x",
                                   service_catalog=expected_service_catalog)
        self.assertThat(ctx.limit, Equals("500"))
        self.assertThat(ctx.marker, Equals("x"))
        self.assertThat(ctx.service_catalog, Equals(expected_service_catalog))

    def test_create(self):
        ctx = context.TroveContext(user='test_user_id',
                                   request_id='test_req_id')
        self.assertThat(ctx.user, Equals('test_user_id'))
        self.assertThat(ctx.request_id, Equals('test_req_id'))
        self.assertThat(ctx.limit, Is(None))
        self.assertThat(ctx.marker, Is(None))
        self.assertThat(ctx.service_catalog, Is(None))

    def test_to_dict(self):
        ctx = context.TroveContext(user='test_user_id',
                                   request_id='test_req_id')
        ctx_dict = ctx.to_dict()
        self.assertThat(ctx_dict.get('user'), Equals('test_user_id'))
        self.assertThat(ctx_dict.get('request_id'), Equals('test_req_id'))

    def test_to_dict_with_notification(self):
        ctx = context.TroveContext(user='test_user_id',
                                   tenant='the_tenant',
                                   request_id='test_req_id')
        ctx.notification = DBaaSInstanceCreate(ctx,
                                               request=Mock())
        ctx_dict = ctx.to_dict()
        self.assertThat(ctx_dict.get('user'), Equals('test_user_id'))
        self.assertThat(ctx_dict.get('request_id'), Equals('test_req_id'))
        self.assertIn('trove_notification', ctx_dict)
        n_dict = ctx_dict['trove_notification']
        self.assertThat(n_dict.get('notification_classname'),
                        Equals('trove.common.notification.'
                               'DBaaSInstanceCreate'))

    def test_create_with_bogus(self):
        with mock.patch('trove.common.context.LOG') as mock_log:
            ctx = context.TroveContext.from_dict(
                {'user': 'test_user_id',
                 'request_id': 'test_req_id',
                 'tenant': 'abc',
                 'blah_blah': 'blah blah'})
            mock_log.warning.assert_called()
            mock_log.warning.assert_called_with('Argument being removed '
                                                'before instantiating '
                                                'TroveContext object - '
                                                '%(key)s = %(value)s',
                                                {'value': 'blah blah',
                                                 'key': 'blah_blah'})
        self.assertThat(ctx.user, Equals('test_user_id'))
        self.assertThat(ctx.request_id, Equals('test_req_id'))
        self.assertThat(ctx.tenant, Equals('abc'))
        self.assertThat(ctx.limit, Is(None))
        self.assertThat(ctx.marker, Is(None))
        self.assertThat(ctx.service_catalog, Is(None))
