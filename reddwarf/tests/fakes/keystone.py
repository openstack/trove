# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import re


class AuthProtocol(object):

    def __init__(self, app, conf):
        self.conf = conf
        self.app = app

    def __call__(self, env, start_response):
        token = self._get_user_token_from_header(env)
        user_headers = self._get_info_from_token(token)
        self._add_headers(env, user_headers)
        return self.app(env, start_response)

    def _header_to_env_var(self, key):
        """Convert header to wsgi env variable.

        :param key: http header name (ex. 'X-Auth-Token')
        :return wsgi env variable name (ex. 'HTTP_X_AUTH_TOKEN')

        """
        return 'HTTP_%s' % key.replace('-', '_').upper()

    def _add_headers(self, env, headers):
        """Add http headers to environment."""
        for (k, v) in headers.iteritems():
            env_key = self._header_to_env_var(k)
            env[env_key] = v

    def get_admin_token(self):
        return "ABCDEF0123456789"

    def _get_info_from_token(self, token):
        if token.startswith("admin"):
            role = "admin,%s" % token
        else:
            role = token
        return {
            'X_IDENTITY_STATUS': 'Confirmed',
            'X_TENANT_ID': token,
            'X_TENANT_NAME': token,
            'X_USER_ID': token,
            'X_USER_NAME': token,
            'X_ROLE': role,
        }

    def _get_header(self, env, key, default=None):
        # Copied from keystone.
        env_key = self._header_to_env_var(key)
        return env.get(env_key, default)

    def _get_user_token_from_header(self, env):
        token = self._get_header(env, 'X-Auth-Token',
                                 self._get_header(env, 'X-Storage-Token'))
        if token:
            return token
        else:
            raise RuntimeError('Unable to find token in headers')


def filter_factory(global_conf, **local_conf):
    """Fakes a keystone filter."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return AuthProtocol(app, conf)
    return auth_filter
