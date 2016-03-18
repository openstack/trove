# Copyright 2015 IBM Corp.
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

from os import path

SERVICE_CANDIDATES = ["couchdb"]
UPDATE_BIND_ADDRESS = (
    "sudo sed -i -r 's/;bind_address = 127.0.0.1/bind_address = 0.0.0.0/' "
    "/etc/couchdb/local.ini")
TIME_OUT = 1200
COUCHDB_HTTPD_PORT = "5984"
COUCHDB_SERVER_STATUS = "curl http://127.0.0.1:" + COUCHDB_HTTPD_PORT
COUCHDB_ADMIN_NAME = 'os_admin'
COUCHDB_CREATE_ADMIN = (
    "curl -X PUT http://127.0.0.1:" + COUCHDB_HTTPD_PORT +
    "/_config/admins/" + COUCHDB_ADMIN_NAME + " -d '\"%(password)s\"'")
COUCHDB_ADMIN_CREDS_FILE = path.join(path.expanduser('~'),
                                     '.os_couchdb_admin_creds.json')
CREATE_USER_COMMAND = (
    "curl -X PUT http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/_users/org.couchdb.user:%(username)s -H \"Accept:"
    " application/json\" -H \"Content-Type: application/json\" -d \'{\"name\""
    ": \"%(username)s\", \"password\": \"%(password)s\", \"roles\": [],"
    " \"type\":\"user\"}\'")
DELETE_REV_ID = (
    "curl -s http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/_users/_all_docs")
DELETE_USER_COMMAND = (
    "curl -X DELETE http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/_users/org.couchdb.user:%(username)s?rev="
    "%(revid)s")
ALL_USERS_COMMAND = (
    "curl -s http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/_users/_all_docs")
DB_ACCESS_COMMAND = (
    "curl -s http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/%(dbname)s/_security")
GRANT_ACCESS_COMMAND = (
    "curl -X PUT http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/%(dbname)s/_security -d \'{\"admins\":{\"names\""
    ":[], \"roles\":[]}, \"members\":{\"" + "names\":[\"%(username)s\"],\""
    "roles\":[]}}\'")
REVOKE_ACCESS_COMMAND = (
    "curl -X PUT http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/%(dbname)s/_security" + " -d \'{\"admins\":{\""
    "names\":[], \"roles\":[]}, \"members\":{\"" + "names\":%(username)s,\""
    "roles\":[]}}\'")
ENABLE_ROOT = (
    "curl -X PUT http://%(admin_name)s:%(admin_password)s@localhost:5984"
    "/_config/admins/root -d '\"%(password)s\"'")
IS_ROOT_ENABLED = (
    "curl -s http://%(admin_name)s:%(admin_password)s@localhost:5984/_config/"
    "admins")
CREATE_DB_COMMAND = (
    "curl -X PUT http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/%(dbname)s")
LIST_DB_COMMAND = (
    "curl -X GET http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/_all_dbs")
DELETE_DB_COMMAND = (
    "curl -X DELETE http://%(admin_name)s:%(admin_password)s@localhost:" +
    COUCHDB_HTTPD_PORT + "/%(dbname)s")
