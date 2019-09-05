# Copyright 2019 Catalyst Cloud Ltd.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.


class FakeNeutronClient(object):
    def __init__(self, context):
        self.context = context

    def show_network(self, *arg, **kwargs):
        return {'network': {'name': 'fake-mgmt-net-name'}}

    def list_networks(self, *arg, **kwargs):
        if 'router:external' in kwargs:
            return {'networks': [{'id': 'fake-public-net-id'}]}

        return {'networks': []}

    def create_port(self, body):
        if 'Management' in body['port'].get('description', ''):
            return {'port': {'id': 'fake-mgmt-port-id'}}

        return {'port': {'id': 'fake-user-port-id'}}

    def delete_port(self, *arg, **kwargs):
        pass

    def list_ports(self, *arg, **kwargs):
        return {'ports': []}

    def create_floatingip(self, *arg, **kwargs):
        pass

    def list_floatingips(self, *arg, **kwargs):
        return {'floatingips': []}

    def update_floatingip(self, *arg, **kwargs):
        pass

    def delete_floatingip(self, *arg, **kwargs):
        pass

    def create_security_group(self, *arg, **kwargs):
        return {'security_group': {'id': 'fake-sg-id'}}

    def create_security_group_rule(self, *arg, **kwargs):
        pass

    def list_security_groups(self, *arg, **kwargs):
        return {'security_groups': []}

    def delete_security_group(self, *arg, **kwargs):
        pass


def fake_create_neutron_client(context, region_name=None):
    return FakeNeutronClient(context)
