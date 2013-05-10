from nose.tools import assert_equal
from nose.tools import assert_false
from nose.tools import assert_true

from proboscis import before_class
from proboscis import test

from reddwarf.openstack.common import timeutils
from reddwarf.tests.util import create_dbaas_client
from reddwarfclient import exceptions
from datetime import datetime
from reddwarf.tests.util.users import Users
from reddwarf.tests.config import CONFIG

GROUP = "dbaas.api.limits"
DEFAULT_RATE = 200
DEFAULT_MAX_VOLUMES = 100
DEFAULT_MAX_INSTANCES = 55
DEFAULT_MAX_BACKUPS = 5


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
                    "services": ["reddwarf"]
                }
            },
            {
                "auth_user": "rate_limit_exceeded",
                "auth_key": "password",
                "tenant": "4050",
                "requirements": {
                    "is_admin": False,
                    "services": ["reddwarf"]
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
    def test_limits_index(self):
        """test_limits_index"""

        limits = self.rd_client.limits.list()
        d = self._get_limits_as_dict(limits)

        # remove the abs_limits from the rate limits
        abs_limits = d.pop("ABSOLUTE", None)
        assert_equal(abs_limits.verb, "ABSOLUTE")
        assert_equal(int(abs_limits.max_instances), DEFAULT_MAX_INSTANCES)
        assert_equal(int(abs_limits.max_backups), DEFAULT_MAX_BACKUPS)
        if CONFIG.reddwarf_volume_support:
            assert_equal(int(abs_limits.max_volumes), DEFAULT_MAX_VOLUMES)

        for k in d:
            assert_equal(d[k].verb, k)
            assert_equal(d[k].unit, "MINUTE")
            assert_true(int(d[k].remaining) <= DEFAULT_RATE)
            assert_true(d[k].nextAvailable is not None)

    @test
    def test_limits_get_remaining(self):
        """test_limits_get_remaining"""

        limits = ()
        for i in xrange(5):
            limits = self.rd_client.limits.list()

        d = self._get_limits_as_dict(limits)
        abs_limits = d["ABSOLUTE"]
        get = d["GET"]

        assert_equal(int(abs_limits.max_instances), DEFAULT_MAX_INSTANCES)
        assert_equal(int(abs_limits.max_backups), DEFAULT_MAX_BACKUPS)
        if CONFIG.reddwarf_volume_support:
            assert_equal(int(abs_limits.max_volumes), DEFAULT_MAX_VOLUMES)
        assert_equal(get.verb, "GET")
        assert_equal(get.unit, "MINUTE")
        assert_true(int(get.remaining) <= DEFAULT_RATE - 5)
        assert_true(get.nextAvailable is not None)

    @test
    def test_limits_exception(self):
        """test_limits_exception"""

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
                if CONFIG.reddwarf_volume_support:
                    assert_equal(int(abs_limits.max_volumes),
                                 DEFAULT_MAX_VOLUMES)

            except exceptions.OverLimit:
                encountered = True

        assert_true(encountered)
        assert_true(int(get.remaining) <= 50)
