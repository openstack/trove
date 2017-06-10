# Copyright 2016 Tesora Inc.
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

from datetime import datetime
from datetime import timedelta
from datetime import tzinfo

from trove.common import timeutils
from trove.tests.unittests import trove_testtools


class bogus_tzinfo(tzinfo):
    """A bogus tzinfo class"""
    def utcoffset(self, dt):
        return timedelta(hours=2)

    def tzname(self, dt):
        return "BOGUS"

    def dst(self, dt):
        return timedelta(hours=1)


class invalid_tzinfo(tzinfo):
    """A bogus tzinfo class"""
    def utcoffset(self, dt):
        return timedelta(hours=25)

    def tzname(self, dt):
        return "INVALID"

    def dst(self, dt):
        return timedelta(hours=25)


class TestTroveTimeutils(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveTimeutils, self).setUp()

    def tearDown(self):
        super(TestTroveTimeutils, self).tearDown()

    def test_utcnow_tz(self):
        dt = timeutils.utcnow()

        self.assertIsNone(dt.tzinfo)

    def test_utcnow_aware_tz(self):
        dt = timeutils.utcnow_aware()

        self.assertEqual(timedelta(0), dt.utcoffset())
        self.assertEqual('Z', dt.tzname())

    def test_isotime(self):
        dt = timeutils.utcnow_aware()

        expected = "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
            dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

        self.assertEqual(expected, timeutils.isotime(dt))

    def test_isotime_subsecond(self):
        dt = timeutils.utcnow_aware()

        expected = "%04d-%02d-%02dT%02d:%02d:%02d.%06dZ" % (
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second,
            dt.microsecond)

        self.assertEqual(expected, timeutils.isotime(dt, subsecond=True))

    def test_isotime_unaware(self):
        dt = timeutils.utcnow()

        expected = "%04d-%02d-%02dT%02d:%02d:%02d.%06dZ" % (
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second,
            dt.microsecond)

        self.assertEqual(expected, timeutils.isotime(dt, subsecond=True))

    def test_isotime_unaware_subsecond(self):
        dt = timeutils.utcnow()

        expected = "%04d-%02d-%02dT%02d:%02d:%02d.%06dZ" % (
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second,
            dt.microsecond)

        self.assertEqual(expected, timeutils.isotime(dt, subsecond=True))

    def test_bogus_unaware(self):
        dt = datetime.now(bogus_tzinfo())

        expected = "%04d-%02d-%02dT%02d:%02d:%02d.%06d+02:00" % (
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second,
            dt.microsecond)

        self.assertEqual(expected, timeutils.isotime(dt, subsecond=True))

    def test_bogus_unaware_subsecond(self):
        dt = datetime.now(bogus_tzinfo())

        expected = "%04d-%02d-%02dT%02d:%02d:%02d.%06d+02:00" % (
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second,
            dt.microsecond)

        self.assertEqual(expected, timeutils.isotime(dt, subsecond=True))

    def test_throws_exception(self):
        dt = datetime.now()
        dt = dt.replace(tzinfo=invalid_tzinfo())

        self.assertRaises(ValueError, timeutils.isotime, dt)
