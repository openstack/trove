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

SERVICE_CANDIDATES = ["couchdb"]
UPDATE_BIND_ADDRESS = (
    "sudo sed -i -r 's/;bind_address = 127.0.0.1/bind_address = 0.0.0.0/' "
    "/etc/couchdb/local.ini")
TIME_OUT = 1200
UPDATE_LIB_DIR_PERMISSIONS = "sudo chmod -R g+rw %(libdir)s"
UPDATE_LOG_DIR_PERMISSIONS = "sudo chmod -R g+rw %(logdir)s"
UPDATE_BIN_DIR_PERMISSIONS = "sudo chmod -R g+rw %(bindir)s"
UPDATE_CONF_DIR_PERMISSIONS = "sudo chmod -R g+rw %(confdir)s"
UPDATE_GROUP_MEMBERSHIP = "sudo usermod -a -G couchdb $(whoami)"
COUCHDB_HTTPD_PORT = "5984"
COUCHDB_SERVER_STATUS = "curl http://127.0.0.1:" + COUCHDB_HTTPD_PORT
