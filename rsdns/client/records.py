# Copyright 2011 OpenStack Foundation
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
Records interface.
"""

import six.moves.urllib.parse as urlparse

from novaclient import base
from rsdns.client.future import FutureResource


class FutureRecord(FutureResource):

    def convert_callback(self, resp, body):
        try:
            list = body['records']
        except NameError:
            raise RuntimeError('Body was missing "records" or "record" key.')
        if len(list) != 1:
            raise RuntimeError('Return result had ' + str(len(list)) +
                               'records, not 1.')
        return Record(self, list[0])

    def response_list_name(self):
        return "records"


class Record(base.Resource):
    """
    A Record is a individual dns record (Cname, A, MX, etc..)
    """

    pass


class RecordsManager(base.ManagerWithFind):
    """
    Manage :class:`Record` resources.
    """
    resource_class = Record

    def create(self, domain, record_name, record_data, record_type,
               record_ttl):
        """
        Create a new Record on the given domain

        :param domain: The ID of the :class:`Domain` to get.
        :param record: The ID of the :class:`Record` to get.
        :rtype: :class:`Record`
        """
        data = {"records": [{"type": record_type, "name": record_name,
                            "data": record_data, "ttl": record_ttl}]}
        resp, body = self.api.client.post("/domains/%s/records" % \
                                          base.getid(domain), body=data)
        if resp.status == 202:
            return FutureRecord(self, **body)
        raise RuntimeError("Did not expect response when creating a DNS "
                            "record %s" % str(resp.status))

    def create_from_list(self, list):
        return [self.resource_class(self, res) for res in list]

    def delete(self, domain_id, record_id):
        self._delete("/domains/%s/records/%s" % (domain_id, record_id))

    def match_record(self, record, name=None, address=None, type=None):
        assert(isinstance(record, Record))
        return (not name or record.name == name) and \
               (not address or record.data == address) and \
               (not type or record.type == type)

    def get(self, domain_id, record_id):
        """
        Get a single record by id.

        :rtype: Single instance of :class:`Record`
        """
        url = "/domains/%s/records" % domain_id
        if record_id:
            url += ("/%s" % record_id)
        resp, body = self.api.client.get(url)
        try:
            item = body
        except IndexError:
            raise RuntimeError('Body was missing record element.')
        return self.resource_class(self, item)

    def list(self, domain_id, record_id=None, record_name=None,
             record_address=None, record_type=None):
        """
        Get a list of all records under a domain.

        :rtype: list of :class:`Record`
        """
        url = "/domains/%s/records" % domain_id
        if record_id:
            url += ("/%s" % record_id)
        offset = 0
        list = []
        while offset is not None:
            next_url = "%s?offset=%d" % (url, offset)
            partial_list, offset = self.page_list(next_url)
            list += partial_list
        all_records = self.create_from_list(list)
        return [record for record in all_records
                if self.match_record(record, record_name, record_address,
                                     record_type)]

    def page_list(self, url):
        """
        Given a URL and an offset, returns a tuple containing a list and the
        next URL.
        """
        resp, body = self.api.client.get(url)
        try:
            list = body['records']
        except NameError:
            raise RuntimeError('Body was missing "records" or "record" key.')
        next_offset = None
        links = body.get('links', [])
        for link in links:
            if link['rel'] == 'next':
                next = link['href']
                params = urlparse.parse_qs(urlparse.urlparse(next).query)
                offset_list = params.get('offset', [])
                if len(offset_list) == 1:
                    next_offset = int(offset_list[0])
                elif len(offset_list) == 0:
                    next_offset = None
                else:
                    raise RuntimeError("Next href had multiple offset params!")
        return (list, next_offset)
