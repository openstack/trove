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


class HostView(object):

    def __init__(self, host):
        self.host = host

    def data(self):
        return {
           'instanceCount': self.host.instance_count,
           'name': self.host.name
        }


class HostDetailedView(object):

    def __init__(self, host):
        self.host = host

    def data(self):
        return {'host': {
            'instances': self.host.instances,
            'name': self.host.name,
            'percentUsed': self.host.percent_used,
            'totalRAM': self.host.total_ram,
            'usedRAM': self.host.used_ram
        }}


class HostsView(object):

    def __init__(self, hosts):
        self.hosts = hosts

    def data(self):
        data = [HostView(host).data() for host in self.hosts]
        return {'hosts': data}
