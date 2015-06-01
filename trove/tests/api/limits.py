# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
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

from datetime import datetime

from nose.tools import assert_equal
from nose.tools import assert_true
from oslo_utils import timeutils
from proboscis import before_class
from proboscis import test
from troveclient.compat import exceptions

from trove.common import cfg
from trove.tests.fakes import limits as fake_limits
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Users


CONF = cfg.CONF

GROUP = "dbaas.api.limits"
DEFAULT_RATE = CONF.http_get_rate
DEFAULT_MAX_VOLUMES = CONF.max_volumes_per_user
DEFAULT_MAX_INSTANCES = CONF.max_instances_per_user
DEFAULT_MAX_BACKUPS = CONF.max_backups_per_user


def ensure_limits_are_not_faked(func):
    def _cd(*args, **kwargs):
        fake_limits.ENABLED = True
        try:
            return func(*args, **kwargs)
        finally:
            fake_limits.ENABLED = False


@test(groups=[GROUP])
class Limits(object):

    @before_class
    def setUp(self):

        users = [
            {
                "auth_user": "rate_limit",
                "auth_key": "password",
                "tenant": "4000",
                "requirements": {
                    "is_admin": False,
                    "services": ["trove"]
                }
            },
            {
                "auth_user": "rate_limit_exceeded",
                "auth_key": "password",
                "tenant": "4050",
                "requirements": {
                    "is_admin": False,
                    "services": ["trove"]
                }
            }]

        self._users = Users(users)

        rate_user = self._get_user('rate_limit')
        self.rd_client = create_dbaas_client(rate_user)

    def _get_user(self, name):
        return self._users.find_user_by_name(name)

    def __is_available(self, next_available):
        dt_next = timeutils.parse_isotime(next_available)
        dt_now = datetime.now()
        return dt_next.time() < dt_now.time()

    def _get_limits_as_dict(self, limits):
        d = {}
        for l in limits:
            d[l.verb] = l
        return d

    @test
    @ensure_limits_are_not_faked
    def test_limits_index(self):
        """Test_limits_index."""

        limits = self.rd_client.limits.list()
        d = self._get_limits_as_dict(limits)

        # remove the abs_limits from the rate limits
        abs_limits = d.pop("ABSOLUTE", None)
        assert_equal(abs_limits.verb, "ABSOLUTE")
        assert_equal(int(abs_limits.max_instances), DEFAULT_MAX_INSTANCES)
        assert_equal(int(abs_limits.max_backups), DEFAULT_MAX_BACKUPS)
        assert_equal(int(abs_limits.max_volumes), DEFAULT_MAX_VOLUMES)

        for k in d:
            assert_equal(d[k].verb, k)
            assert_equal(d[k].unit, "MINUTE")
            assert_true(int(d[k].remaining) <= DEFAULT_RATE)
            assert_true(d[k].nextAvailable is not None)

    @test
    @ensure_limits_are_not_faked
    def test_limits_get_remaining(self):
        """Test_limits_get_remaining."""

        limits = ()
        for i in xrange(5):
            limits = self.rd_client.limits.list()

        d = self._get_limits_as_dict(limits)
        abs_limits = d["ABSOLUTE"]
        get = d["GET"]

        assert_equal(int(abs_limits.max_instances), DEFAULT_MAX_INSTANCES)
        assert_equal(int(abs_limits.max_backups), DEFAULT_MAX_BACKUPS)
        assert_equal(int(abs_limits.max_volumes), DEFAULT_MAX_VOLUMES)
        assert_equal(get.verb, "GET")
        assert_equal(get.unit, "MINUTE")
        assert_true(int(get.remaining) <= DEFAULT_RATE - 5)
        assert_true(get.nextAvailable is not None)

    @test
    @ensure_limits_are_not_faked
    def test_limits_exception(self):
        """Test_limits_exception."""

        # use a different user to avoid throttling tests run out of order
        rate_user_exceeded = self._get_user('rate_limit_exceeded')
        rd_client = create_dbaas_client(rate_user_exceeded)

        get = None
        encountered = False
        for i in xrange(DEFAULT_RATE + 50):
            try:
                limits = rd_client.limits.list()
                d = self._get_limits_as_dict(limits)
                get = d["GET"]
                abs_limits = d["ABSOLUTE"]

                assert_equal(get.verb, "GET")
                assert_equal(get.unit, "MINUTE")
                assert_equal(int(abs_limits.max_instances),
                             DEFAULT_MAX_INSTANCES)
                assert_equal(int(abs_limits.max_backups),
                             DEFAULT_MAX_BACKUPS)
                assert_equal(int(abs_limits.max_volumes),
                             DEFAULT_MAX_VOLUMES)

            except exceptions.OverLimit:
                encountered = True

        assert_true(encountered)
        assert_true(int(get.remaining) <= 50)
