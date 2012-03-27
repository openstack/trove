# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Model classes that form the core of instances functionality."""

import logging

from reddwarf import db

from reddwarf.common import config
from reddwarf.guestagent import api as guest_api

CONFIG = config.Config
LOG = logging.getLogger(__name__)


class User(object):

    _data_fields = ['name', 'password', 'databases']

    def __init__(self, name, password, databases):
        self.name = name
        self.password = password
        self.databases = databases

    @classmethod
    def create(cls, context, instance_id, users):
        guest_api.API().create_user(context, instance_id, users)


class Users(object):

    @classmethod
    def load(cls, context, instance_id):
        user_list = guest_api.API().list_users(context, instance_id)
        return [User(user['_name'], user['_password'], user['_databases'])
                for user in user_list]
