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
"""I totally stole most of this from melange, thx guys!!!"""

import eventlet.wsgi
import logging
import paste.urlmap
import re
import traceback
import webob
import webob.dec
import webob.exc

from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.openstack.common import wsgi as openstack_wsgi


Router = openstack_wsgi.Router
Server = openstack_wsgi.Server
Debug = openstack_wsgi.Debug
Middleware = openstack_wsgi.Middleware
JSONDictSerializer = openstack_wsgi.JSONDictSerializer

eventlet.patcher.monkey_patch(all=False, socket=True)

LOG = logging.getLogger('reddwarf.common.wsgi')


def versioned_urlmap(*args, **kwargs):
    urlmap = paste.urlmap.urlmap_factory(*args, **kwargs)
    return VersionedURLMap(urlmap)


class VersionedURLMap(object):

    def __init__(self, urlmap):
        self.urlmap = urlmap

    def __call__(self, environ, start_response):
        req = Request(environ)

        if req.url_version is None and req.accept_version is not None:
            version = "/v" + req.accept_version
            http_exc = webob.exc.HTTPNotAcceptable(_("version not supported"))
            app = self.urlmap.get(version, Fault(http_exc))
        else:
            app = self.urlmap

        return app(environ, start_response)


class Request(openstack_wsgi.Request):

    @property
    def params(self):
        return utils.stringify_keys(super(Request, self).params)

    def best_match_content_type(self, supported_content_types=None):
        """Determine the most acceptable content-type.

        Based on the query extension then the Accept header.

        """
        parts = self.path.rsplit('.', 1)

        if len(parts) > 1:
            format = parts[1]
            if format in ['json', 'xml']:
                return 'application/{0}'.format(parts[1])

        ctypes = {'application/vnd.openstack.reddwarf+json': "application/json",
                  'application/vnd.openstack.reddwarf+xml': "application/xml",
                  'application/json': "application/json",
                  'application/xml': "application/xml"}
        bm = self.accept.best_match(ctypes.keys())

        return ctypes.get(bm, 'application/json')

    @utils.cached_property
    def accept_version(self):
        accept_header = self.headers.get('ACCEPT', "")
        accept_version_re = re.compile(".*?application/vnd.openstack.reddwarf"
                                       "(\+.+?)?;"
                                       "version=(?P<version_no>\d+\.?\d*)")

        match = accept_version_re.search(accept_header)
        return  match.group("version_no") if match else None

    @utils.cached_property
    def url_version(self):
        versioned_url_re = re.compile("/v(?P<version_no>\d+\.?\d*)")
        match = versioned_url_re.search(self.path)
        return match.group("version_no") if match else None


class Result(object):

    def __init__(self, data, status=200):
        self._data = data
        self.status = status

    def data(self, serialization_type):
        if (serialization_type == "application/xml" and
            hasattr(self._data, "data_for_xml")):
            return self._data.data_for_xml()
        if hasattr(self._data, "data_for_json"):
            return self._data.data_for_json()
        return self._data


class Resource(openstack_wsgi.Resource):

    def __init__(self, controller, deserializer, serializer,
                 exception_map=None):
        exception_map = exception_map or {}
        self.model_exception_map = self._invert_dict_list(exception_map)
        super(Resource, self).__init__(controller, deserializer, serializer)

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, request):
        return super(Resource, self).__call__(request)

    def execute_action(self, action, request, **action_args):
        if getattr(self.controller, action, None) is None:
            return Fault(webob.exc.HTTPNotFound())
        try:
            result = super(Resource, self).execute_action(action,
                request,
                **action_args)
            if type(result) is dict:
                result = Result(result)
            return result

        except exception.ReddwarfError as reddwarf_error:
            LOG.debug(traceback.format_exc())
            httpError = self._get_http_error(reddwarf_error)
            return Fault(httpError(str(reddwarf_error), request=request))
        except webob.exc.HTTPError as http_error:
            LOG.debug(traceback.format_exc())
            return Fault(http_error)
        except Exception as error:
            LOG.exception(error)
            return Fault(webob.exc.HTTPInternalServerError(str(error),
                request=request))

    def _get_http_error(self, error):
        return self.model_exception_map.get(type(error),
            webob.exc.HTTPBadRequest)

    def _invert_dict_list(self, exception_dict):
        """Flattens values of keys and inverts keys and values.

        Example:
        {'x':[1,2,3],'y':[4,5,6]} converted to
        {1:'x',2:'x',3:'x',4:'y',5:'y',6:'y'}

        """
        inverted_dict = {}
        for key, value_list in exception_dict.items():
            for value in value_list:
                inverted_dict[value] = key
        return inverted_dict


class Controller(object):
    """Base controller that creates a Resource with default serializers."""

    exception_map = {}

    def create_resource(self):
        serializer = ReddwarfResponseSerializer(
            body_serializers={'application/xml': ReddwarfXMLDictSerializer()})
        return Resource(self,
            openstack_wsgi.RequestDeserializer(),
            serializer,
            self.exception_map)


class ReddwarfXMLDictSerializer(openstack_wsgi.XMLDictSerializer):

    def _to_xml_node(self, doc, metadata, nodename, data):
        if hasattr(data, "to_xml"):
            return data.to_xml()
        return super(ReddwarfXMLDictSerializer, self)._to_xml_node(doc,
            metadata,
            nodename,
            data)


class ReddwarfResponseSerializer(openstack_wsgi.ResponseSerializer):

    def serialize_body(self, response, data, content_type, action):
        if isinstance(data, Result):
            data = data.data(content_type)
        super(ReddwarfResponseSerializer, self).serialize_body(response,
            data,
            content_type,
            action)

    def serialize_headers(self, response, data, action):
        super(ReddwarfResponseSerializer, self).serialize_headers(response,
            data,
            action)
        if isinstance(data, Result):
            response.status = data.status


class Fault(webob.exc.HTTPException):
    """Error codes for API faults."""

    def __init__(self, exception):
        """Create a Fault for the given webob.exc.exception."""

        self.wrapped_exc = exception

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, req):
        """Generate a WSGI response based on the exception passed to ctor."""

        # Replace the body with fault details.
        fault_name = self.wrapped_exc.__class__.__name__
        if fault_name.startswith("HTTP"):
            fault_name = fault_name[4:]
        fault_data = {
            fault_name: {
                'code': self.wrapped_exc.status_int,
                'message': self.wrapped_exc.explanation,
                'detail': self.wrapped_exc.detail,
                }
        }

        # 'code' is an attribute on the fault tag itself
        metadata = {'attributes': {fault_name: 'code'}}
        content_type = req.best_match_content_type()
        serializer = {
            'application/xml': openstack_wsgi.XMLDictSerializer(metadata),
            'application/json': openstack_wsgi.JSONDictSerializer(),
            }[content_type]

        self.wrapped_exc.body = serializer.serialize(fault_data, content_type)
        self.wrapped_exc.content_type = content_type
        return self.wrapped_exc