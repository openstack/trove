from nose.tools import assert_equal
from nose.tools import assert_false
from nose.tools import assert_true

from proboscis import before_class
from proboscis import test

from reddwarf.openstack.common import timeutils
from reddwarf.tests.util import create_dbaas_client
from reddwarf.tests.util import test_config
from reddwarfclient import exceptions

from datetime import datetime

GROUP = "dbaas.api.limits"
DEFAULT_RATE = 200
# Note: This should not be enabled until rd-client merges
RD_CLIENT_OK = False


@test(groups=[GROUP])
class Limits(object):

    @before_class
    def setUp(self):
        rate_user = self._get_user('rate_limit')
        self.rd_client = create_dbaas_client(rate_user)

    def _get_user(self, name):
        return test_config.users.find_user_by_name(name)

    def _get_next_available(self, resource):
        return resource.__dict__['next-available']

    def __is_available(self, next_available):
        dt_next = timeutils.parse_isotime(next_available)
        dt_now = datetime.now()
        return dt_next.time() < dt_now.time()

    @test(enabled=RD_CLIENT_OK)
    def test_limits_index(self):
        """test_limits_index"""
        r1, r2, r3, r4 = self.rd_client.limits.index()

        assert_equal(r1.verb, "POST")
        assert_equal(r1.unit, "MINUTE")
        assert_true(r1.remaining <= DEFAULT_RATE)

        next_available = self._get_next_available(r1)
        assert_true(next_available is not None)

        assert_equal(r2.verb, "PUT")
        assert_equal(r2.unit, "MINUTE")
        assert_true(r2.remaining <= DEFAULT_RATE)

        next_available = self._get_next_available(r2)
        assert_true(next_available is not None)

        assert_equal(r3.verb, "DELETE")
        assert_equal(r3.unit, "MINUTE")
        assert_true(r3.remaining <= DEFAULT_RATE)

        next_available = self._get_next_available(r3)
        assert_true(next_available is not None)

        assert_equal(r4.verb, "GET")
        assert_equal(r4.unit, "MINUTE")
        assert_true(r4.remaining <= DEFAULT_RATE)

        next_available = self._get_next_available(r4)
        assert_true(next_available is not None)

    @test(enabled=RD_CLIENT_OK)
    def test_limits_get_remaining(self):
        """test_limits_get_remaining"""
        gets = None
        for i in xrange(5):
            r1, r2, r3, r4 = self.rd_client.limits.index()
            gets = r4

        assert_equal(gets.verb, "GET")
        assert_equal(gets.unit, "MINUTE")
        assert_true(gets.remaining <= DEFAULT_RATE - 5)

        next_available = self._get_next_available(gets)
        assert_true(next_available is not None)

    @test(enabled=RD_CLIENT_OK)
    def test_limits_exception(self):
        """test_limits_exception"""

        # use a different user to avoid throttling tests run out of order
        rate_user_exceeded = self._get_user('rate_limit_exceeded')
        rd_client = create_dbaas_client(rate_user_exceeded)

        gets = None
        encountered = False
        for i in xrange(DEFAULT_RATE + 50):
            try:
                r1, r2, r3, r4 = rd_client.limits.index()
                gets = r4
                assert_equal(gets.verb, "GET")
                assert_equal(gets.unit, "MINUTE")

            except exceptions.OverLimit:
                encountered = True

        assert_true(encountered)
        assert_true(gets.remaining <= 50)
