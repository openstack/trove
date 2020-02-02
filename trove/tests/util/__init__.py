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
"""

import subprocess
try:
    EVENT_AVAILABLE = True
except ImportError:
    EVENT_AVAILABLE = False

import glanceclient
from keystoneauth1.identity import v3
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutron_client
from novaclient import client as nova_client
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail
from proboscis import SkipTest
from six.moves.urllib.parse import unquote
from sqlalchemy import create_engine
from sqlalchemy.sql.expression import text
import tenacity
from troveclient.compat import Dbaas

from trove.common import cfg
from trove.common.utils import import_class
from trove.common.utils import import_object
from trove.tests.config import CONFIG as test_config
from trove.tests.util.client import TestClient
from trove.tests.util import mysql
from trove.tests.util import test_config as CONFIG
from trove.tests.util.users import Requirements


WHITE_BOX = test_config.white_box
FLUSH = text("FLUSH PRIVILEGES;")
CONF = cfg.CONF


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


def create_keystone_session(user):
    auth = v3.Password(username=user.auth_user,
                       password=user.auth_key,
                       project_id=user.tenant_id,
                       user_domain_name='Default',
                       project_domain_name='Default',
                       auth_url=test_config.auth_url)
    return session.Session(auth=auth)


def create_nova_client(user, service_type=None):
    if not service_type:
        service_type = CONF.nova_compute_service_type
    openstack = nova_client.Client(
        CONF.nova_client_version,
        username=user.auth_user,
        password=user.auth_key,
        user_domain_name='Default',
        project_id=user.tenant_id,
        auth_url=CONFIG.auth_url,
        service_type=service_type, os_cache=False,
        cacert=test_config.values.get('cacert', None)
    )

    return TestClient(openstack)


def create_neutron_client(user):
    sess = create_keystone_session(user)
    client = neutron_client.Client(
        session=sess,
        service_type=CONF.neutron_service_type,
        region_name=CONFIG.trove_client_region_name,
        insecure=CONF.neutron_api_insecure,
        endpoint_type=CONF.neutron_endpoint_type
    )

    return TestClient(client)


def create_glance_client(user):
    sess = create_keystone_session(user)
    glance = glanceclient.Client(CONF.glance_client_version, session=sess)

    return TestClient(glance)


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
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    return output


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


# TODO(cp16net): DO NOT USE needs to be removed
def mysql_connection():
    cls = CONFIG.get('mysql_connection',
                     "local.MySqlConnection")
    if cls == "local.MySqlConnection":
        return MySqlConnection()
    return import_object(cls)()


class MySqlConnection(object):
    def assert_fails(self, ip, user_name, password):
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

    @tenacity.retry(
        wait=tenacity.wait_fixed(3),
        stop=tenacity.stop_after_attempt(5),
        reraise=True
    )
    def create(self, ip, user_name, password):
        print("Connecting mysql, host: %s, user: %s, password: %s" %
              (ip, user_name, password))

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
        return create_engine("mysql+pymysql://%s:%s@%s:3306" %
                             (user, password, host),
                             pool_recycle=1800, echo=True)
