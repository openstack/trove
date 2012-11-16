# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

# This emulates the old way we did things, which was to load the config
# as a module.
# TODO(tim.simpson): Change all references from "test_config" to CONFIG.
from reddwarf.tests.config import CONFIG as test_config

import re
import subprocess
import sys
import time

try:
    from eventlet import event
    from eventlet import greenthread
    EVENT_AVAILABLE = True
except ImportError:
    EVENT_AVAILABLE = False

from sqlalchemy import create_engine

from reddwarfclient import exceptions

from proboscis import test
from proboscis.asserts import assert_false
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail
from proboscis.asserts import ASSERTION_ERROR
from proboscis import SkipTest
from reddwarfclient import Dbaas
from reddwarfclient.client import ReddwarfHTTPClient
from reddwarf.tests.util import test_config
from reddwarf.tests.util.client import TestClient as TestClient
from reddwarf.tests.util.users import Requirements


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
    """Creates a rich client for the RedDwarf API using the test config."""
    auth_strategy = None

    kwargs = {
        'service_type': 'reddwarf',
        'insecure': test_config.values['reddwarf_client_insecure'],
    }

    def set_optional(kwargs_name, test_conf_name):
        value = test_config.values.get(test_conf_name, None)
        if value is not None:
            kwargs[kwargs_name] = value
    force_url = 'override_reddwarf_api_url' in test_config.values

    service_url = test_config.get('override_reddwarf_api_url', None)
    if user.requirements.is_admin:
        service_url = test_config.get('override_admin_reddwarf_api_url',
                                      service_url)
    if service_url:
        kwargs['service_url'] = service_url

    auth_strategy = None
    if user.requirements.is_admin:
        auth_strategy = test_config.get('admin_auth_strategy',
                                        test_config.auth_strategy)
    else:
        auth_strategy = test_config.auth_strategy
    set_optional('region_name', 'reddwarf_client_region_name')
    if test_config.values.get('override_reddwarf_api_url_append_tenant',
                              False):
        kwargs['service_url'] += "/" + user.tenant

    if auth_strategy == 'fake':
        from reddwarfclient import auth

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
        auth_url = test_config.reddwarf_auth_url
    else:
        auth_url = test_config.values.get('reddwarf_admin_auth_url',
                                          test_config.reddwarf_auth_url)

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
                       service_type=service_type)
    openstack.authenticate()
    return TestClient(openstack)


def process(cmd):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    result = process.communicate()
    return result


def string_in_list(str, substr_list):
    """Returns True if the string appears in the list."""
    return any([str.find(x) >= 0 for x in substr_list])


class PollTimeOut(RuntimeError):
    message = _("Polling request timed out.")


# Without event let, this just calls time.sleep.
def poll_until(retriever, condition=lambda value: value,
               sleep_time=1, time_out=None):
    """Retrieves object until it passes condition, then returns it.

    If time_out_limit is passed in, PollTimeOut will be raised once that
    amount of time is eclipsed.

    """
    start_time = time.time()

    def check_timeout():
        if time_out is not None and time.time() > start_time + time_out:
            raise PollTimeOut

    while True:
        obj = retriever()
        if condition(obj):
            return
        check_timeout()
        time.sleep(sleep_time)


class LocalSqlClient(object):
    """A sqlalchemy wrapper to manage transactions"""

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
        except:
            self.trans.rollback()
            self.trans = None
            raise
