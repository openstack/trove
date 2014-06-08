# Copyright (c) 2011 OpenStack Foundation
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

"""
:mod:`tests` -- Utility methods for tests.
===================================

.. automodule:: utils
   :platform: Unix
   :synopsis: Tests for Nova.
.. moduleauthor:: Nirmal Ranganathan <nirmal.ranganathan@rackspace.com>
.. moduleauthor:: Tim Simpson <tim.simpson@rackspace.com>
"""

import subprocess

from trove.tests.config import CONFIG as test_config
from urllib import unquote

try:
    EVENT_AVAILABLE = True
except ImportError:
    EVENT_AVAILABLE = False

from sqlalchemy import create_engine

from troveclient.compat import exceptions

from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail
from proboscis import SkipTest
from troveclient.compat import Dbaas
from trove.tests.util import test_config as CONFIG
from trove.tests.util.client import TestClient as TestClient
from trove.tests.util.users import Requirements
from trove.common.utils import import_object
from trove.common.utils import import_class


WHITE_BOX = test_config.white_box


def assert_http_code(expected_http_code, func, *args, **kwargs):
    try:
        rtn_value = func(*args, **kwargs)
        assert_equal(
            expected_http_code,
            200,
            "Expected the function to return http code %s but instead got "
            "no error (code 200?)." % expected_http_code)
        return rtn_value
    except exceptions.ClientException as ce:
        assert_equal(
            expected_http_code,
            ce.code,
            "Expected the function to return http code %s but instead got "
            "code %s." % (expected_http_code, ce.code))


def create_client(*args, **kwargs):
    """
    Using the User Requirements as arguments, finds a user and grabs a new
    DBAAS client.
    """
    reqs = Requirements(*args, **kwargs)
    user = test_config.users.find_user(reqs)
    return create_dbaas_client(user)


def create_dbaas_client(user):
    """Creates a rich client for the Trove API using the test config."""
    auth_strategy = None

    kwargs = {
        'service_type': 'database',
        'insecure': test_config.values['trove_client_insecure'],
    }

    def set_optional(kwargs_name, test_conf_name):
        value = test_config.values.get(test_conf_name, None)
        if value is not None:
            kwargs[kwargs_name] = value
    force_url = 'override_trove_api_url' in test_config.values

    service_url = test_config.get('override_trove_api_url', None)
    if user.requirements.is_admin:
        service_url = test_config.get('override_admin_trove_api_url',
                                      service_url)
    if service_url:
        kwargs['service_url'] = service_url

    auth_strategy = None
    if user.requirements.is_admin:
        auth_strategy = test_config.get('admin_auth_strategy',
                                        test_config.auth_strategy)
    else:
        auth_strategy = test_config.auth_strategy
    set_optional('region_name', 'trove_client_region_name')
    if test_config.values.get('override_trove_api_url_append_tenant',
                              False):
        kwargs['service_url'] += "/" + user.tenant

    if auth_strategy == 'fake':
        from troveclient.compat import auth

        class FakeAuth(auth.Authenticator):

            def authenticate(self):
                class FakeCatalog(object):
                    def __init__(self, auth):
                        self.auth = auth

                    def get_public_url(self):
                        return "%s/%s" % (test_config.dbaas_url,
                                          self.auth.tenant)

                    def get_token(self):
                        return self.auth.tenant

                return FakeCatalog(self)

        auth_strategy = FakeAuth

    if auth_strategy:
        kwargs['auth_strategy'] = auth_strategy

    if not user.requirements.is_admin:
        auth_url = test_config.trove_auth_url
    else:
        auth_url = test_config.values.get('trove_admin_auth_url',
                                          test_config.trove_auth_url)

    if test_config.values.get('trove_client_cls'):
        cls_name = test_config.trove_client_cls
        kwargs['client_cls'] = import_class(cls_name)

    dbaas = Dbaas(user.auth_user, user.auth_key, tenant=user.tenant,
                  auth_url=auth_url, **kwargs)
    dbaas.authenticate()
    with Check() as check:
        check.is_not_none(dbaas.client.auth_token, "Auth token not set!")
        if not force_url and user.requirements.is_admin:
            expected_prefix = test_config.dbaas_url
            actual = dbaas.client.service_url
            msg = "Dbaas management url was expected to start with %s, but " \
                  "was %s." % (expected_prefix, actual)
            check.true(actual.startswith(expected_prefix), msg)
    return TestClient(dbaas)


def create_nova_client(user, service_type=None):
    """Creates a rich client for the Nova API using the test config."""
    if test_config.nova_client is None:
        raise SkipTest("No nova_client info specified in the Test Config "
                       "so this test will be skipped.")
    from novaclient.v1_1.client import Client
    if not service_type:
        service_type = test_config.nova_client['nova_service_type']
    openstack = Client(user.auth_user, user.auth_key,
                       user.tenant, test_config.nova_client['auth_url'],
                       service_type=service_type, no_cache=True)
    openstack.authenticate()
    return TestClient(openstack)


def dns_checker(mgmt_instance):
    """Given a MGMT instance, ensures DNS provisioning worked.

    Uses a helper class which, given a mgmt instance (returned by the mgmt
    API) can confirm that the DNS record provisioned correctly.
    """
    if CONFIG.values.get('trove_dns_checker') is not None:
        checker = import_class(CONFIG.trove_dns_checker)
        checker()(mgmt_instance)
    else:
        raise SkipTest("Can't access DNS system to check if DNS provisioned.")


def process(cmd):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    result = process.communicate()
    return result


def string_in_list(str, substr_list):
    """Returns True if the string appears in the list."""
    return any([str.find(x) >= 0 for x in substr_list])


def unquote_user_host(user_hostname):
    unquoted = unquote(user_hostname)
    if '@' not in unquoted:
        return unquoted, '%'
    if unquoted.endswith('@'):
        return unquoted, '%'
    splitup = unquoted.split('@')
    host = splitup[-1]
    user = '@'.join(splitup[:-1])
    return user, host


def iso_time(time_string):
    """Return a iso formated datetime: 2013-04-15T19:50:23Z."""
    ts = time_string.replace(' ', 'T')
    try:
        micro = ts.rindex('.')
        ts = ts[:micro]
    except ValueError:
        pass
    return '%sZ' % ts


def assert_contains(exception_message, substrings):
    for substring in substrings:
        assert_true(substring in exception_message,
                    message="'%s' not in '%s'"
                    % (substring, exception_message))


# TODO(dukhlov): Still required by trove integration
# Should be removed after trove integration fix
# https://bugs.launchpad.net/trove-integration/+bug/1228306


#TODO(cp16net): DO NOT USE needs to be removed
def mysql_connection():
    cls = CONFIG.get('mysql_connection',
                     "local.MySqlConnection")
    if cls == "local.MySqlConnection":
        return MySqlConnection()
    return import_object(cls)()


class MySqlConnection(object):

    def assert_fails(self, ip, user_name, password):
        from trove.tests.util import mysql
        try:
            with mysql.create_mysql_connection(ip, user_name, password):
                pass
            fail("Should have failed to connect: mysql --host %s -u %s -p%s"
                 % (ip, user_name, password))
        except mysql.MySqlPermissionsFailure:
            return  # Good, this is what we wanted.
        except mysql.MySqlConnectionFailure as mcf:
            fail("Expected to see permissions failure. Instead got message:"
                 "%s" % mcf.message)

    def create(self, ip, user_name, password):
        from trove.tests.util import mysql
        return mysql.create_mysql_connection(ip, user_name, password)


class LocalSqlClient(object):
    """A sqlalchemy wrapper to manage transactions."""

    def __init__(self, engine, use_flush=True):
        self.engine = engine
        self.use_flush = use_flush

    def __enter__(self):
        self.conn = self.engine.connect()
        self.trans = self.conn.begin()
        return self.conn

    def __exit__(self, type, value, traceback):
        if self.trans:
            if type is not None:  # An error occurred
                self.trans.rollback()
            else:
                if self.use_flush:
                    self.conn.execute(FLUSH)
                self.trans.commit()
        self.conn.close()

    def execute(self, t, **kwargs):
        try:
            return self.conn.execute(t, kwargs)
        except Exception:
            self.trans.rollback()
            self.trans = None
            raise

    @staticmethod
    def init_engine(user, password, host):
        return create_engine("mysql://%s:%s@%s:3306" %
                             (user, password, host),
                             pool_recycle=1800, echo=True)
