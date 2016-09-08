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

import bisect
import collections
import six.moves.urllib.parse as urllib_parse


def url_quote(s):
    if s is None:
        return s
    return urllib_parse.quote(str(s))


def paginate_list(li, limit=None, marker=None, include_marker=False,
                  key=lambda x: x):
    """Sort the given list and return a sublist containing a page of items.

    :param list li:             The list to be paginated.
    :param int limit:           Maximum number of items to be returned.
    :param marker:              Key of the first item to appear on the sublist.
    :param bool include_marker: Include the marker value itself in the sublist.
    :param lambda key:          Sorting expression.
    :return:
    """
    sli = sorted(li, key=key)
    index = [key(item) for item in sli]
    if marker is None:
        marker = ''
    if include_marker:
        pos = bisect.bisect_left(index, marker)
    else:
        pos = bisect.bisect(index, marker)

    if limit and pos + limit < len(sli):
        page = sli[pos:pos + limit]
        return page, key(page[-1])
    else:
        return sli[pos:], None


def paginate_object_list(li, attr_name, limit=None, marker=None,
                         include_marker=False):
    """Wrapper for paginate_list to handle lists of generic objects paginated
    based on an attribute.
    """
    return paginate_list(li, limit=limit, marker=marker,
                         include_marker=include_marker,
                         key=lambda x: getattr(x, attr_name))


def paginate_dict_list(li, key, limit=None, marker=None, include_marker=False):
    """Wrapper for paginate_list to handle lists of dicts paginated
    based on a key.
    """
    return paginate_list(li, limit=limit, marker=marker,
                         include_marker=include_marker,
                         key=lambda x: x[key])


class PaginatedDataView(object):

    def __init__(self, collection_type, collection, current_page_url,
                 next_page_marker=None):
        self.collection_type = collection_type
        self.collection = collection
        self.current_page_url = current_page_url
        self.next_page_marker = url_quote(next_page_marker)

    def data(self):
        return {self.collection_type: self.collection,
                'links': self._links,
                }

    def _links(self):
        if not self.next_page_marker:
            return []
        app_url = AppUrl(self.current_page_url)
        next_url = app_url.change_query_params(marker=self.next_page_marker)
        next_link = {
            'rel': 'next',
            'href': str(next_url),
        }
        return [next_link]


class SimplePaginatedDataView(object):
    # In some cases, we can't create a PaginatedDataView because
    # we don't have a collection query object to create a view on.
    # In that case, we have to supply the URL and collection manually.

    def __init__(self, url, name, view, marker):
        self.url = url
        self.name = name
        self.view = view
        self.marker = url_quote(marker)

    def data(self):
        if not self.marker:
            return self.view.data()

        app_url = AppUrl(self.url)
        next_url = str(app_url.change_query_params(marker=self.marker))
        next_link = {'rel': 'next',
                     'href': next_url}
        view_data = {self.name: self.view.data()[self.name],
                     'links': [next_link]}
        return view_data


class AppUrl(object):

    def __init__(self, url):
        self.url = url

    def __str__(self):
        return self.url

    def change_query_params(self, **kwargs):
        # Seeks out the query params in a URL and changes/appends to them
        # from the kwargs given. So change_query_params(foo='bar')
        # would remove from the URL any old instance of foo=something and
        # then add &foo=bar to the URL.
        parsed_url = urllib_parse.urlparse(self.url)
        # Build a dictionary out of the query parameters in the URL
        # with an OrderedDict to preserve the order of the URL.
        query_params = collections.OrderedDict(
            urllib_parse.parse_qsl(parsed_url.query))
        # Use kwargs to change or update any values in the query dict.
        query_params.update(kwargs)

        # Build a new query based on the updated query dict.
        new_query_params = urllib_parse.urlencode(query_params)
        return self.__class__(
            # Force HTTPS.
            urllib_parse.ParseResult('https',
                                     parsed_url.netloc, parsed_url.path,
                                     parsed_url.params, new_query_params,
                                     parsed_url.fragment).geturl())
