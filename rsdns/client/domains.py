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

"""
Domains interface.
"""

from novaclient import base

import os
from rsdns.client.future import FutureResource


class Domain(base.Resource):
    """
    A Domain has a name and stores records.  In the API they are id'd by ints.
    """

    def response_list_name(self):
        return "domains"


class FutureDomain(FutureResource):

    def convert_callback(self, resp, body):
        return Domain(self.manager, body)

    def response_list_name(self):
        return "domains"


class DomainsManager(base.ManagerWithFind):
    """
    Manage :class:`Domain` resources.
    """
    resource_class = Domain

    def create(self, name):
        """Not implemented / needed yet."""
        if os.environ.get("ADD_DOMAINS", "False") == 'True':
            accountId = self.api.client.accountId
            data = {"domains":
                        [
                            {"name": name,
                             "ttl":"5600",
                             "emailAddress":"dbaas_dns@rackspace.com",
                            }
                        ]
                    }
            resp, body = self.api.client.post("/domains", body=data)
            if resp.status == 202:
                return FutureDomain(self, **body)
            raise RuntimeError("Did not expect response " + str(resp.status))
        else:
            raise NotImplementedError("No need for create.")

    def create_from_list(self, list):
        return [self.resource_class(self, res) for res in list]

    def delete(self, *args, **kwargs):
        """Not implemented / needed yet."""
        raise NotImplementedError("No need for create.")

    def list(self, name=None):
        """
        Get a list of all domains.

        :rtype: list of :class:`Domain`
        """
        url = "/domains"
        if name:
            url += "?name=" + name
        resp, body = self.api.client.get(url)
        try:
            list = body['domains']
        except KeyError:
            raise RuntimeError('Body was missing "domains" key.')
        return self.create_from_list(list)
