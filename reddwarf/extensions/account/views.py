# Copyright 2012 OpenStack LLC.
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

from collections import defaultdict


def tree():
    return defaultdict(tree)


class AccountView(object):

    def __init__(self, account, instances):
        self.account = account
        self.instances = instances

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(InstanceView(instance).data())
        res = tree()
        res['account']['id'] = self.account.id
        res['account']['instances'] = data
        return res


class InstanceView(object):

    def __init__(self, instance):
        self.instance = instance

    def data(self):
        res = tree()
        res['id'] = self.instance.id
        res['status'] = self.instance.status
        res['name'] = self.instance.name
        res['host'] = self.instance.host
        return res
