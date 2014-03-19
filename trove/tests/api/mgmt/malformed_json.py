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

from collections import deque
from proboscis import test
from proboscis import asserts
from proboscis import after_class
from proboscis import before_class
from trove.tests.config import CONFIG
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import VOLUME_SUPPORT

from trove.tests.util.users import Requirements
from trove.tests.util import assert_contains
from trove.tests.util import create_dbaas_client
from trove.common.utils import poll_until


@test(groups=["dbaas.api.mgmt.malformed_json"])
class MalformedJson(object):
    @before_class
    def setUp(self):
        self.reqs = Requirements(is_admin=False)
        self.user = CONFIG.users.find_user(self.reqs)
        self.dbaas = create_dbaas_client(self.user)
        volume = None
        if VOLUME_SUPPORT:
            volume = {"size": 1}
        self.instance = self.dbaas.instances.create(
            name="qe_instance",
            flavor_id=instance_info.dbaas_flavor_href,
            volume=volume,
            databases=[{"name": "firstdb", "character_set": "latin2",
                        "collate": "latin2_general_ci"}])

    @after_class
    def tearDown(self):
        self.dbaas.instances.delete(self.instance)

    @test
    def test_bad_instance_data(self):
        databases = "foo"
        users = "bar"
        try:
            self.dbaas.instances.create("bad_instance", 3, 3,
                                        databases=databases, users=users)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Create instance failed with code %s,"
                                 " exception %s" % (httpCode, e))
            databases = "u'foo'"
            users = "u'bar'"
            assert_contains(
                e.message,
                ["Validation error:",
                 "instance['databases'] %s is not of type 'array'" % databases,
                 "instance['users'] %s is not of type 'array'" % users,
                 "instance['volume'] 3 is not of type 'object'"])

    @test
    def test_bad_database_data(self):
        _bad_db_data = "{foo}"
        try:
            self.dbaas.databases.create(self.instance.id, _bad_db_data)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Create database failed with code %s, "
                                 "exception %s" % (httpCode, e))
            _bad_db_data = "u'{foo}'"
            asserts.assert_equal(e.message,
                                 "Validation error: "
                                 "databases %s is not of type 'array'" %
                                 _bad_db_data)

    @test
    def test_bad_user_data(self):

        def format_path(values):
            values = list(values)
            msg = "%s%s" % (values[0],
                            ''.join(['[%r]' % i for i in values[1:]]))
            return msg

        _user = []
        _user_name = "F343jasdf"
        _user.append({"name12": _user_name,
                      "password12": "password"})
        try:
            self.dbaas.users.create(self.instance.id, _user)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Create user failed with code %s, "
                                 "exception %s" % (httpCode, e))
            err_1 = format_path(deque(('users', 0)))
            assert_contains(
                e.message,
                ["Validation error:",
                 "%(err_1)s 'name' is a required property" % {'err_1': err_1},
                 "%(err_1)s 'password' is a required property"
                 % {'err_1': err_1}])

    @test
    def test_bad_resize_instance_data(self):
        def _check_instance_status():
            inst = self.dbaas.instances.get(self.instance)
            if inst.status == "ACTIVE":
                return True
            else:
                return False

        poll_until(_check_instance_status)
        try:
            self.dbaas.instances.resize_instance(self.instance.id, "bad data")
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Resize instance failed with code %s, "
                                 "exception %s" % (httpCode, e))

    @test
    def test_bad_resize_vol_data(self):
        def _check_instance_status():
            inst = self.dbaas.instances.get(self.instance)
            if inst.status == "ACTIVE":
                return True
            else:
                return False

        poll_until(_check_instance_status)
        data = "bad data"
        try:
            self.dbaas.instances.resize_volume(self.instance.id, data)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Resize instance failed with code %s, "
                                 "exception %s" % (httpCode, e))
            data = "u'bad data'"
            assert_contains(
                e.message,
                ["Validation error:",
                 "resize['volume']['size'] %s is not valid under "
                 "any of the given schemas" % data,
                 "%s is not of type 'integer'" % data,
                 "%s does not match '[0-9]+'" % data])

    @test
    def test_bad_change_user_password(self):
        password = ""
        users = [{"name": password}]

        def _check_instance_status():
            inst = self.dbaas.instances.get(self.instance)
            if inst.status == "ACTIVE":
                return True
            else:
                return False

        poll_until(_check_instance_status)
        try:
            self.dbaas.users.change_passwords(self.instance, users)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Change usr/passwd failed with code %s, "
                                 "exception %s" % (httpCode, e))
            password = "u''"
            assert_contains(
                e.message,
                ["Validation error: users[0] 'password' "
                 "is a required property",
                 "users[0]['name'] %s is too short" % password,
                 "users[0]['name'] %s does not match "
                 "'^.*[0-9a-zA-Z]+.*$'" % password])

    @test
    def test_bad_grant_user_access(self):
        dbs = []

        def _check_instance_status():
            inst = self.dbaas.instances.get(self.instance)
            if inst.status == "ACTIVE":
                return True
            else:
                return False

        poll_until(_check_instance_status)
        try:
            self.dbaas.users.grant(self.instance, self.user, dbs)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Grant user access failed with code %s, "
                                 "exception %s" % (httpCode, e))

    @test
    def test_bad_revoke_user_access(self):
        db = ""

        def _check_instance_status():
            inst = self.dbaas.instances.get(self.instance)
            if inst.status == "ACTIVE":
                return True
            else:
                return False

        poll_until(_check_instance_status)
        try:
            self.dbaas.users.revoke(self.instance, self.user, db)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 404,
                                 "Revoke user access failed w/code %s, "
                                 "exception %s" % (httpCode, e))
            asserts.assert_equal(e.message, "The resource could not be found.")

    @test
    def test_bad_body_flavorid_create_instance(self):

        flavorId = ["?"]
        try:
            self.dbaas.instances.create("test_instance",
                                        flavorId,
                                        2)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Create instance failed with code %s, "
                                 "exception %s" % (httpCode, e))
            flavorId = [u'?']
            assert_contains(
                e.message,
                ["Validation error:",
                 "instance['flavorRef'] %s is not valid "
                 "under any of the given schemas" % flavorId,
                 "%s is not of type 'string'" % flavorId,
                 "%s is not of type 'string'" % flavorId,
                 "%s is not of type 'integer'" % flavorId,
                 "instance['volume'] 2 is not of type 'object'"])

    @test
    def test_bad_body_datastore_create_instance(self):

        datastore = "*"
        datastore_version = "*"
        try:
            self.dbaas.instances.create("test_instance",
                                        3, {"size": 2},
                                        datastore=datastore,
                                        datastore_version=datastore_version)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Create instance failed with code %s, "
                                 "exception %s" % (httpCode, e))
            assert_contains(
                e.message,
                ["Validation error:",
                 "instance['datastore']['type']"
                 " u'%s' does not match"
                 " '^.*[0-9a-zA-Z]+.*$'" % datastore,
                 "instance['datastore']['version'] u'%s' "
                 "does not match '^.*[0-9a-zA-Z]+.*$'" % datastore_version])

    @test
    def test_bad_body_volsize_create_instance(self):
        volsize = "h3ll0"
        try:
            self.dbaas.instances.create("test_instance",
                                        "1",
                                        volsize)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            asserts.assert_equal(httpCode, 400,
                                 "Create instance failed with code %s, "
                                 "exception %s" % (httpCode, e))
            volsize = "u'h3ll0'"
            asserts.assert_equal(e.message,
                                 "Validation error: "
                                 "instance['volume'] %s is not of "
                                 "type 'object'" % volsize)
