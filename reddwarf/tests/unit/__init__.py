# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import json
import webtest

from reddwarf import tests
from reddwarf.common import config
from reddwarf.common import utils
from reddwarf.common import wsgi
from reddwarf.db import db_api


# TODO(hub-cap): we will probably use this later
# def sanitize(data):
#     serializer = wsgi.JSONDictSerializer()
#     return json.loads(serializer.serialize(data))


class TestApp(webtest.TestApp):

    def post_json(self, url, body=None, **kwargs):
        kwargs['content_type'] = "application/json"
        return self.post(url, json.dumps(body), **kwargs)

    def put_json(self, url, body=None, **kwargs):
        kwargs['content_type'] = "application/json"
        return self.put(url, json.dumps(body), **kwargs)


def setup():
    options = {"config_file": tests.test_config_file()}
    conf = config.Config.load_paste_config("reddwarfapp", options, None)

    db_api.db_reset(conf)
