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

import urllib
import urlparse
from xml.dom import minidom


class AtomLink(object):

    def __init__(self, rel, href):
        self.rel = rel
        self.href = href

    def to_xml(self):
        ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
        doc = minidom.Document()
        atom_elem = doc.createElementNS(ATOM_NAMESPACE, "link")
        atom_elem.setAttribute("rel", self.rel)
        atom_elem.setAttribute("href", self.href)
        return atom_elem


class PaginatedDataView(object):

    def __init__(self, collection_type, collection, current_page_url,
                 next_page_marker=None):
        self.collection_type = collection_type
        self.collection = collection
        self.current_page_url = current_page_url
        self.next_page_marker = next_page_marker

    def data_for_json(self):
        json_dict = {self.collection_type: self.collection}
        if self._links():
            links_key = self.collection_type + "_links"
            json_dict[links_key] = self._links()
        return json_dict

    def data_for_xml(self):
        atom_links = [AtomLink(link['rel'], link['href'])
                           for link in self._links()]
        return {self.collection_type: self.collection + atom_links}

    def _create_link(self, marker):
        app_url = AppUrl(self.current_page_url)
        return str(app_url.change_query_params(marker=marker))

    def _links(self):
        if not self.next_page_marker:
            return []
        next_link = dict(rel='next',
                         href=self._create_link(self.next_page_marker))
        return [next_link]


class AppUrl(object):

    def __init__(self, url):
        self.url = url

    def __str__(self):
        return self.url

    def change_query_params(self, **kwargs):
        parsed_url = urlparse.urlparse(self.url)
        query_params = dict(urlparse.parse_qsl(parsed_url.query))
        query_params.update(kwargs)

        new_query_params = urllib.urlencode(query_params)
        return self.__class__(
            urlparse.ParseResult(parsed_url.scheme,
                                 parsed_url.netloc, parsed_url.path,
                                 parsed_url.params, new_query_params,
                                 parsed_url.fragment).geturl())