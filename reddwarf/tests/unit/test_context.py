# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright 2011 OpenStack LLC.
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

import logging
import unittest

from reddwarf.common import context

AUTH_TOK = "auth-token"
LOG = logging.getLogger(__name__)
TENANT = "tenant"
USER = "user"


class ContextTest(unittest.TestCase):

    def test_get_context_as_dict(self):
        ctx = context.ReddwarfContext(user=USER, tenant=TENANT,
                                      is_admin=True, show_deleted=True,
                                      read_only=True, auth_tok=AUTH_TOK)
        ctx_dict = ctx.to_dict()
        self.assertEqual(ctx_dict['user'], USER)
        self.assertEqual(ctx_dict['tenant'], TENANT)
        self.assertEqual(ctx_dict['is_admin'], True)
        self.assertEqual(ctx_dict['show_deleted'], True)
        self.assertEqual(ctx_dict['read_only'], True)
        self.assertEqual(ctx_dict['auth_tok'], AUTH_TOK)

    def test_creating_context(self):
        tmp_ctx_dict = {
            'user': USER,
            'tenant': TENANT,
            'is_admin': True,
            'show_deleted': True,
            'read_only': True,
            'auth_tok': AUTH_TOK,
        }
        tmp_ctx = context.ReddwarfContext.from_dict(tmp_ctx_dict)
        self.assertEqual(tmp_ctx.user, USER)
        self.assertEqual(tmp_ctx.tenant, TENANT)
        self.assertEqual(tmp_ctx.is_admin, True)
        self.assertEqual(tmp_ctx.show_deleted, True)
        self.assertEqual(tmp_ctx.read_only, True)
        self.assertEqual(tmp_ctx.auth_tok, AUTH_TOK)
