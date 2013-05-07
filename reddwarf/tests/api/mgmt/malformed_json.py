from proboscis import test
from proboscis.asserts import *
from proboscis import after_class
from proboscis import before_class
from proboscis.asserts import Check
from reddwarf.tests.config import CONFIG
from reddwarfclient import exceptions
import json
import requests

from reddwarf.tests.util.users import Requirements
from reddwarf.tests.util import create_dbaas_client
from reddwarf.tests.util import poll_until
from nose.plugins.skip import SkipTest


@test(groups=["dbaas.api.mgmt.malformed_json"])
class MalformedJson(object):

    @before_class
    def setUp(self):
        self.reqs = Requirements(is_admin=False)
        self.user = CONFIG.users.find_user(self.reqs)
        self.dbaas = create_dbaas_client(self.user)
        self.instance = self.dbaas.instances.create(
            name="qe_instance",
            flavor_id=1,
            volume={"size": 1},
            databases=[{"name": "firstdb", "character_set": "latin2",
                        "collate": "latin2_general_ci"}])

    @after_class
    def tearDown(self):
        self.dbaas.instances.delete(self.instance)

    @test
    def test_bad_instance_data(self):
        raise SkipTest("Please see Launchpad Bug #1177969")
        try:
            self.dbaas.instances.create("bad_instance", 3, 3,
                                        databases="foo",
                                        users="bar")
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            assert_true(httpCode == 400,
                        "Create instance failed with code %s, exception %s"
                        % (httpCode, e))

    @test
    def test_bad_database_data(self):
        raise SkipTest("Please see Launchpad Bug #1177969")
        _bad_db_data = "{foo}"
        try:
            self.dbaas.databases.create(self.instance.id, _bad_db_data)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            assert_true(httpCode == 400,
                        "Create database failed with code %s, exception %s"
                        % (httpCode, e))

    @test
    def test_bad_user_data(self):
        _user = []
        _user_name = "F343jasdf"
        _user.append({"name12": _user_name,
                      "password12": "password"})
        try:
            self.dbaas.users.create(self.instance.id, _user)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            assert_true(httpCode == 400,
                        "Create user failed with code %s, exception %s"
                        % (httpCode, e))

    @test
    def test_bad_resize_instance_data(self):
        raise SkipTest("Please see Launchpad Bug #1177969")

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
            assert_true(httpCode == 400,
                        "Resize instance failed with code %s, exception %s"
                        % (httpCode, e))

    @test
    def test_bad_resize_vol_data(self):
        def _check_instance_status():
            inst = self.dbaas.instances.get(self.instance)
            if inst.status == "ACTIVE":
                return True
            else:
                return False
        poll_until(_check_instance_status)
        try:
            self.dbaas.instances.resize_volume(self.instance.id, "bad data")
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            assert_true(httpCode == 400,
                        "Resize instance failed with code %s, exception %s"
                        % (httpCode, e))

    @test
    def test_bad_change_user_password(self):
        users = [{"name": ""}]

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
            assert_true(httpCode == 400,
                        "Change usr/passwd failed with code %s, exception %s" %
                        (httpCode, e))

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
            assert_true(httpCode == 400,
                        "Grant user access failed with code %s, exception %s" %
                        (httpCode, e))

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
            assert_true(httpCode == 404,
                        "Revoke user access failed w/code %s, exception %s" %
                        (httpCode, e))

    @test
    def test_bad_body_flavorid_create_instance(self):
        raise SkipTest("Please see Launchpad Bug #1177969")
        flavorId = ["?"]
        try:
            self.dbaas.instances.create("test_instance",
                                        flavorId,
                                        2)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            assert_true(httpCode == 400,
                        "Create instance failed with code %s, exception %s" %
                        (httpCode, e))

    @test
    def test_bad_body_volsize_create_instance(self):
        raise SkipTest("Please see Launchpad Bug #1177969")
        volsize = ("h3ll0")
        try:
            self.dbaas.instances.create("test_instance",
                                        "1",
                                        volsize)
        except Exception as e:
            resp, body = self.dbaas.client.last_response
            httpCode = resp.status
            assert_true(httpCode == 400,
                        "Create instance failed with code %s, exception %s" %
                        (httpCode, e))
