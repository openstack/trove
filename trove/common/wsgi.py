# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
"""Wsgi helper utilities for trove"""

import eventlet.wsgi
import math
import jsonschema
import paste.urlmap
import re
import time
import traceback
import uuid
import webob
import webob.dec
import webob.exc
from lxml import etree
from xml.dom import minidom

from trove.common import context as rd_context
from trove.common import exception
from trove.common import utils
from trove.openstack.common.gettextutils import _
from trove.openstack.common import jsonutils

from trove.openstack.common import pastedeploy
from trove.openstack.common import service
from trove.openstack.common import wsgi as openstack_wsgi
from trove.openstack.common import log as logging
from trove.common import cfg

CONTEXT_KEY = 'trove.context'
Router = openstack_wsgi.Router
Debug = openstack_wsgi.Debug
Middleware = openstack_wsgi.Middleware
JSONDictSerializer = openstack_wsgi.JSONDictSerializer
XMLDictSerializer = openstack_wsgi.XMLDictSerializer
XMLDeserializer = openstack_wsgi.XMLDeserializer
RequestDeserializer = openstack_wsgi.RequestDeserializer

eventlet.patcher.monkey_patch(all=False, socket=True)

LOG = logging.getLogger('trove.common.wsgi')

CONF = cfg.CONF

XMLNS = 'http://docs.openstack.org/database/api/v1.0'
CUSTOM_PLURALS_METADATA = {'databases': '', 'users': ''}
CUSTOM_SERIALIZER_METADATA = {
    'instance': {
        'status': '',
        'hostname': '',
        'id': '',
        'name': '',
        'created': '',
        'updated': '',
        'host': '',
        'server_id': '',
        #mgmt/instance
        'local_id': '',
        'task_description': '',
        'deleted': '',
        'deleted_at': '',
        'tenant_id': '',
    },
    'volume': {
        'size': '',
        'used': '',
        #mgmt/instance
        'id': '',
    },
    'flavor': {'id': '', 'ram': '', 'name': ''},
    'link': {'href': '', 'rel': ''},
    'database': {'name': ''},
    'user': {'name': '', 'password': '', 'host': ''},
    'account': {'id': ''},
    'security_group': {'id': '', 'name': '', 'description': '', 'user': '',
                       'tenant_id': ''},
    'security_group_rule': {'id': '', 'group_id': '', 'protocol': '',
                            'from_port': '', 'to_port': '', 'cidr': ''},
    'security_group_instance_association': {'id': '', 'security_group_id': '',
                                            'instance_id': ''},
    # mgmt/host
    'host': {'instanceCount': '', 'name': '', 'usedRAM': '', 'totalRAM': '',
             'percentUsed': ''},
    # mgmt/storage
    'capacity': {'available': '', 'total': ''},
    'provision': {'available': '', 'total': '', 'percent': ''},
    'device': {'used': '', 'name': '', 'type': ''},
    # mgmt/account
    'account': {'id': '', 'num_instances': ''},
    # mgmt/quotas
    'quotas': {'instances': '', 'volumes': '', 'backups': ''},
    #mgmt/instance
    'guest_status': {'state_description': ''},
    #mgmt/instance/diagnostics
    'diagnostics': {'vmHwm': '', 'vmPeak': '', 'vmSize': '', 'threads': '',
                    'version': '', 'vmRss': '', 'fdSize': ''},
    #mgmt/instance/root
    'root_history': {'enabled': '', 'id': '', 'user': ''},

}


def versioned_urlmap(*args, **kwargs):
    urlmap = paste.urlmap.urlmap_factory(*args, **kwargs)
    return VersionedURLMap(urlmap)


def launch(app_name, port, paste_config_file, data={},
           host='0.0.0.0', backlog=128, threads=1000, workers=None):
    """Launches a wsgi server based on the passed in paste_config_file.

      Launch provides a easy way to create a paste app from the config
      file and launch it via the service launcher. It takes care of
      all of the plumbing. The only caveat is that the paste_config_file
      must be a file that paste.deploy can find and handle. There is
      a helper method in cfg.py that finds files.

      Example:
        conf_file = CONF.find_file(CONF.api_paste_config)
        launcher = wsgi.launch('myapp', CONF.bind_port, conf_file)
        launcher.wait()

    """
    app = pastedeploy.paste_deploy_app(paste_config_file, app_name, data)
    server = openstack_wsgi.Service(app, port, host=host,
                                    backlog=backlog, threads=threads)
    return service.launch(server, workers)


# Note: taken from Nova
def serializers(**serializers):
    """Attaches serializers to a method.

    This decorator associates a dictionary of serializers with a
    method.  Note that the function attributes are directly
    manipulated; the method is not wrapped.
    """

    def decorator(func):
        if not hasattr(func, 'wsgi_serializers'):
            func.wsgi_serializers = {}
        func.wsgi_serializers.update(serializers)
        return func

    return decorator


class TroveMiddleware(Middleware):
    # Note: taken from nova
    @classmethod
    def factory(cls, global_config, **local_config):
        """Used for paste app factories in paste.deploy config files.

        Any local configuration (that is, values under the [filter:APPNAME]
        section of the paste config) will be passed into the `__init__` method
        as kwargs.

        A hypothetical configuration would look like:

            [filter:analytics]
            redis_host = 127.0.0.1
            paste.filter_factory = nova.api.analytics:Analytics.factory

        which would result in a call to the `Analytics` class as

            import nova.api.analytics
            analytics.Analytics(app_from_paste, redis_host='127.0.0.1')

        You could of course re-implement the `factory` method in subclasses,
        but using the kwarg passing it shouldn't be necessary.

        """

        def _factory(app):
            return cls(app, **local_config)

        return _factory


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


class Router(openstack_wsgi.Router):
    # Original router did not allow for serialization of the 404 error.
    # To fix this the _dispatch was modified to use Fault() objects.
    @staticmethod
    @webob.dec.wsgify
    def _dispatch(req):
        """
        Called by self._router after matching the incoming request to a route
        and putting the information into req.environ.  Either returns 404
        or the routed WSGI app's response.
        """

        match = req.environ['wsgiorg.routing_args'][1]
        if not match:
            return Fault(webob.exc.HTTPNotFound())
        app = match['controller']
        return app


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

        ctypes = {
            'application/vnd.openstack.trove+json': "application/json",
            'application/vnd.openstack.trove+xml': "application/xml",
            'application/json': "application/json",
            'application/xml': "application/xml",
        }
        bm = self.accept.best_match(ctypes.keys())

        return ctypes.get(bm, 'application/json')

    @utils.cached_property
    def accept_version(self):
        accept_header = self.headers.get('ACCEPT', "")
        accept_version_re = re.compile(".*?application/vnd.openstack.trove"
                                       "(\+.+?)?;"
                                       "version=(?P<version_no>\d+\.?\d*)")

        match = accept_version_re.search(accept_header)
        return match.group("version_no") if match else None

    @utils.cached_property
    def url_version(self):
        versioned_url_re = re.compile("/v(?P<version_no>\d+\.?\d*)")
        match = versioned_url_re.search(self.path)
        return match.group("version_no") if match else None


class Result(object):
    """A result whose serialization is compatable with JSON and XML.

    This class is used by TroveResponseSerializer, which calls the
    data method to grab a JSON or XML specific dictionary which it then
    passes on to be serialized.

    """

    def __init__(self, data, status=200):
        self._data = data
        self.status = status

    def data(self, serialization_type):
        """Return an appropriate serialized type for the body.

        In both cases a dictionary is returned. With JSON it maps directly,
        while with XML the dictionary is expected to have a single key value
        which becomes the root element.

        """
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
            self.controller.validate_request(action, action_args)
            result = super(Resource, self).execute_action(
                action,
                request,
                **action_args)
            if type(result) is dict:
                result = Result(result)
            return result

        except exception.TroveError as trove_error:
            LOG.debug(traceback.format_exc())
            LOG.debug("Caught Trove Error %s", trove_error)
            httpError = self._get_http_error(trove_error)
            LOG.debug("Mapped Error to %s", httpError)
            return Fault(httpError(str(trove_error), request=request))
        except webob.exc.HTTPError as http_error:
            LOG.debug(traceback.format_exc())
            return Fault(http_error)
        except Exception as error:
            exception_uuid = str(uuid.uuid4())
            LOG.exception(exception_uuid + ": " + str(error))
            return Fault(webob.exc.HTTPInternalServerError(
                "Internal Server Error. Please keep this ID to help us "
                "figure out what went wrong: (%s)" % exception_uuid,
                request=request))

    def _get_http_error(self, error):
        return self.model_exception_map.get(type(error),
                                            webob.exc.HTTPBadRequest)

    def _invert_dict_list(self, exception_dict):
        """Flattens values of keys and inverts keys and values.

        Example:
        {'x': [1, 2, 3], 'y': [4, 5, 6]} converted to
        {1: 'x', 2: 'x', 3: 'x', 4: 'y', 5: 'y', 6: 'y'}

        """
        inverted_dict = {}
        for key, value_list in exception_dict.items():
            for value in value_list:
                inverted_dict[value] = key
        return inverted_dict

    def serialize_response(self, action, action_result, accept):
        # If an exception is raised here in the base class, it is swallowed,
        # and the action_result is returned as-is. For us, that's bad news -
        # we never want that to happen except in the case of webob types.
        # So we override the behavior here so we can at least log it (raising
        # an exception in the base class creates a circular reference issue).
        try:
            return super(Resource, self).serialize_response(
                action, action_result, accept)
        except Exception as ex:
            # The super class code seems designed to either serialize things
            # or pass them back if they're webobs.
            if not isinstance(action_result, webob.Response):
                LOG.error("unserializable result detected! "
                          "Exception type: %s Message: %s" % (type(ex), ex))
                raise


class Controller(object):
    """Base controller that creates a Resource with default serializers."""

    exception_map = {
        webob.exc.HTTPUnprocessableEntity: [
            exception.UnprocessableEntity,
        ],
        webob.exc.HTTPUnauthorized: [
            exception.Forbidden,
            exception.SwiftAuthError,
        ],
        webob.exc.HTTPBadRequest: [
            exception.InvalidModelError,
            exception.BadRequest,
            exception.CannotResizeToSameSize,
            exception.BadValue,
            exception.DatabaseAlreadyExists,
            exception.UserAlreadyExists,
            exception.LocalStorageNotSpecified,
        ],
        webob.exc.HTTPNotFound: [
            exception.NotFound,
            exception.ComputeInstanceNotFound,
            exception.ModelNotFoundError,
            exception.UserNotFound,
            exception.DatabaseNotFound,
            exception.QuotaResourceUnknown,
            exception.BackupFileNotFound
        ],
        webob.exc.HTTPConflict: [
            exception.BackupNotCompleteError,
        ],
        webob.exc.HTTPRequestEntityTooLarge: [
            exception.OverLimit,
            exception.QuotaExceeded,
            exception.VolumeQuotaExceeded,
        ],
        webob.exc.HTTPServerError: [
            exception.VolumeCreationFailure,
            exception.UpdateGuestError,
        ],
        webob.exc.HTTPNotImplemented: [
            exception.VolumeNotSupported,
            exception.LocalStorageNotSupported
        ],
    }

    schemas = {}

    @classmethod
    def get_schema(cls, action, body):
        LOG.debug("Getting schema for %s:%s" %
                  (cls.__class__.__name__, action))
        if cls.schemas:
            matching_schema = cls.schemas.get(action, {})
            if matching_schema:
                LOG.debug("Found Schema: %s" % matching_schema.get("name",
                                                                   "none"))
            return matching_schema

    @staticmethod
    def format_validation_msg(errors):
        # format path like object['field1'][i]['subfield2']
        messages = []
        for error in errors:
            path = list(error.path)
            f_path = "%s%s" % (path[0],
                               ''.join(['[%r]' % i for i in path[1:]]))
            messages.append("%s %s" % (f_path, error.message))
            for suberror in sorted(error.context, key=lambda e: e.schema_path):
                messages.append(suberror.message)
        error_msg = "; ".join(messages)
        return "Validation error: %s" % error_msg

    def validate_request(self, action, action_args):
        body = action_args.get('body', {})
        schema = self.get_schema(action, body)
        if schema:
            validator = jsonschema.Draft4Validator(schema)
            if not validator.is_valid(body):
                errors = sorted(validator.iter_errors(body),
                                key=lambda e: e.path)
                error_msg = self.format_validation_msg(errors)
                LOG.info(error_msg)
                raise exception.BadRequest(message=error_msg)

    def create_resource(self):
        serializer = TroveResponseSerializer(
            body_serializers={'application/xml': TroveXMLDictSerializer()})
        return Resource(
            self,
            TroveRequestDeserializer(),
            serializer,
            self.exception_map)

    def _extract_limits(self, params):
        return dict([(key, params[key]) for key in params.keys()
                     if key in ["limit", "marker"]])


class TroveRequestDeserializer(RequestDeserializer):
    """Break up a Request object into more useful pieces."""

    def __init__(self, body_deserializers=None, headers_deserializer=None,
                 supported_content_types=None):
        super(TroveRequestDeserializer, self).__init__(
            body_deserializers,
            headers_deserializer,
            supported_content_types)

        self.body_deserializers['application/xml'] = TroveXMLDeserializer()


class TroveXMLDeserializer(XMLDeserializer):
    def __init__(self, metadata=None):
        """
        :param metadata: information needed to deserialize xml into
                         a dictionary.
        """
        metadata = metadata or {}
        metadata['plurals'] = CUSTOM_PLURALS_METADATA
        super(TroveXMLDeserializer, self).__init__(metadata)

    def default(self, datastring):
        # Sanitize the newlines
        # hub-cap: This feels wrong but minidom keeps the newlines
        # and spaces as childNodes which is expected behavior.
        return {'body': self._from_xml(re.sub(r'((?<=>)\s+)*\n*(\s+(?=<))*',
                                              '', datastring))}

    def _from_xml_node(self, node, listnames):
        """Convert a minidom node to a simple Python type.

           Overridden from openstack deserializer to skip xmlns attributes and
           remove certain unicode characters

        :param listnames: list of XML node names whose subnodes should
                          be considered list items.

        """

        if len(node.childNodes) == 1 and node.childNodes[0].nodeType == 3:
            return node.childNodes[0].nodeValue
        elif node.nodeName in listnames:
            return [self._from_xml_node(n, listnames) for n in node.childNodes]
        else:
            result = dict()
            for attr in node.attributes.keys():
                if attr == 'xmlns':
                    continue
                result[attr] = node.attributes[attr].nodeValue
            for child in node.childNodes:
                if child.nodeType != node.TEXT_NODE:
                    result[child.nodeName] = self._from_xml_node(child,
                                                                 listnames)
            return result


class TroveXMLDictSerializer(openstack_wsgi.XMLDictSerializer):
    def __init__(self, metadata=None, xmlns=None):
        super(TroveXMLDictSerializer, self).__init__(metadata, XMLNS)

    def default(self, data):
        # We expect data to be a dictionary containing a single key as the XML
        # root, or two keys, the later being "links."
        # We expect data to contain a single key which is the XML root,
        has_links = False
        root_key = None
        for key in data:
            if key == "links":
                has_links = True
            elif root_key is None:
                root_key = key
            else:
                msg = "Xml issue: multiple root keys found in dict!: %s" % data
                LOG.error(msg)
                raise RuntimeError(msg)
        if root_key is None:
            msg = "Missing root key in dict: %s" % data
            LOG.error(msg)
            raise RuntimeError(msg)
        doc = minidom.Document()
        node = self._to_xml_node(doc, self.metadata, root_key, data[root_key])
        if has_links:
            # Create a links element, and mix it into the node element.
            links_node = self._to_xml_node(doc, self.metadata,
                                           'links', data['links'])
            node.appendChild(links_node)
        return self.to_xml_string(node)

    def _to_xml_node(self, doc, metadata, nodename, data):
        metadata['attributes'] = CUSTOM_SERIALIZER_METADATA
        if hasattr(data, "to_xml"):
            return data.to_xml()
        return super(TroveXMLDictSerializer, self)._to_xml_node(
            doc,
            metadata,
            nodename,
            data)


class TroveResponseSerializer(openstack_wsgi.ResponseSerializer):
    def serialize_body(self, response, data, content_type, action):
        """Overrides body serialization in openstack_wsgi.ResponseSerializer.

        If the "data" argument is the Result class, its data
        method is called and *that* is passed to the superclass implementation
        instead of the actual data.

        """
        if isinstance(data, Result):
            data = data.data(content_type)
        super(TroveResponseSerializer, self).serialize_body(
            response,
            data,
            content_type,
            action)

    def serialize_headers(self, response, data, action):
        super(TroveResponseSerializer, self).serialize_headers(
            response,
            data,
            action)
        if isinstance(data, Result):
            response.status = data.status


class Fault(webob.exc.HTTPException):
    """Error codes for API faults."""

    code_wrapper = {
        400: webob.exc.HTTPBadRequest,
        401: webob.exc.HTTPUnauthorized,
        403: webob.exc.HTTPUnauthorized,
        404: webob.exc.HTTPNotFound,
    }

    resp_codes = [int(code) for code in code_wrapper.keys()]

    def __init__(self, exception):
        """Create a Fault for the given webob.exc.exception."""

        self.wrapped_exc = exception

    @staticmethod
    def _get_error_name(exc):
        # Displays a Red Dwarf specific error name instead of a webob exc name.
        named_exceptions = {
            'HTTPBadRequest': 'badRequest',
            'HTTPUnauthorized': 'unauthorized',
            'HTTPForbidden': 'forbidden',
            'HTTPNotFound': 'itemNotFound',
            'HTTPMethodNotAllowed': 'badMethod',
            'HTTPRequestEntityTooLarge': 'overLimit',
            'HTTPUnsupportedMediaType': 'badMediaType',
            'HTTPInternalServerError': 'instanceFault',
            'HTTPNotImplemented': 'notImplemented',
            'HTTPServiceUnavailable': 'serviceUnavailable',
        }
        name = exc.__class__.__name__
        if name in named_exceptions:
            return named_exceptions[name]
            # If the exception isn't in our list, at least strip off the
        # HTTP from the name, and then drop the case on the first letter.
        name = name.split("HTTP").pop()
        name = name[:1].lower() + name[1:]
        return name

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, req):
        """Generate a WSGI response based on the exception passed to ctor."""

        # Replace the body with fault details.
        fault_name = Fault._get_error_name(self.wrapped_exc)
        fault_data = {
            fault_name: {
                'code': self.wrapped_exc.status_int,
            }
        }
        if self.wrapped_exc.detail:
            fault_data[fault_name]['message'] = self.wrapped_exc.detail
        else:
            fault_data[fault_name]['message'] = self.wrapped_exc.explanation

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


class ContextMiddleware(openstack_wsgi.Middleware):
    def __init__(self, application):
        self.admin_roles = CONF.admin_roles
        super(ContextMiddleware, self).__init__(application)

    def _extract_limits(self, params):
        return dict([(key, params[key]) for key in params.keys()
                     if key in ["limit", "marker"]])

    def process_request(self, request):
        tenant_id = request.headers.get('X-Tenant-Id', None)
        auth_token = request.headers["X-Auth-Token"]
        user_id = request.headers.get('X-User-ID', None)
        roles = request.headers.get('X-Role', '').split(',')
        is_admin = False
        for role in roles:
            if role.lower() in self.admin_roles:
                is_admin = True
                break
        limits = self._extract_limits(request.params)
        context = rd_context.TroveContext(auth_token=auth_token,
                                          tenant=tenant_id,
                                          user=user_id,
                                          is_admin=is_admin,
                                          limit=limits.get('limit'),
                                          marker=limits.get('marker'))
        request.environ[CONTEXT_KEY] = context

    @classmethod
    def factory(cls, global_config, **local_config):
        def _factory(app):
            LOG.debug(_("Created context middleware with config: %s") %
                      local_config)
            return cls(app)

        return _factory


class FaultWrapper(openstack_wsgi.Middleware):
    """Calls down the middleware stack, making exceptions into faults."""

    @webob.dec.wsgify(RequestClass=openstack_wsgi.Request)
    def __call__(self, req):
        try:
            resp = req.get_response(self.application)
            if resp.status_int in Fault.resp_codes:
                for (header, value) in resp._headerlist:
                    if header == "Content-Type" and \
                            value == "text/plain; charset=UTF-8":
                        return Fault(Fault.code_wrapper[resp.status_int]())
                return resp
            return resp
        except Exception as ex:
            LOG.exception(_("Caught error: %s"), unicode(ex))
            exc = webob.exc.HTTPInternalServerError()
            return Fault(exc)

    @classmethod
    def factory(cls, global_config, **local_config):
        def _factory(app):
            return cls(app)
        return _factory


# ported from Nova
class OverLimitFault(webob.exc.HTTPException):
    """
    Rate-limited request response.
    """

    def __init__(self, message, details, retry_time):
        """
        Initialize new `OverLimitFault` with relevant information.
        """
        hdrs = OverLimitFault._retry_after(retry_time)
        self.wrapped_exc = webob.exc.HTTPRequestEntityTooLarge(headers=hdrs)
        self.content = {"overLimit": {"code": self.wrapped_exc.status_int,
                                      "message": message,
                                      "details": details,
                                      "retryAfter": hdrs['Retry-After'],
                                      },
                        }

    @staticmethod
    def _retry_after(retry_time):
        delay = int(math.ceil(retry_time - time.time()))
        retry_after = delay if delay > 0 else 0
        headers = {'Retry-After': '%d' % retry_after}
        return headers

    @webob.dec.wsgify(RequestClass=Request)
    def __call__(self, request):
        """
        Return the wrapped exception with a serialized body conforming to our
        error format.
        """
        content_type = request.best_match_content_type()
        metadata = {"attributes": {"overLimit": ["code", "retryAfter"]}}

        xml_serializer = XMLDictSerializer(metadata, XMLNS)
        serializer = {'application/xml': xml_serializer,
                      'application/json': JSONDictSerializer(),
                      }[content_type]

        content = serializer.serialize(self.content)
        self.wrapped_exc.body = content
        self.wrapped_exc.content_type = content_type

        return self.wrapped_exc


class ActionDispatcher(object):
    """Maps method name to local methods through action name."""

    def dispatch(self, *args, **kwargs):
        """Find and call local method."""
        action = kwargs.pop('action', 'default')
        action_method = getattr(self, str(action), self.default)
        return action_method(*args, **kwargs)

    def default(self, data):
        raise NotImplementedError()


class DictSerializer(ActionDispatcher):
    """Default request body serialization."""

    def serialize(self, data, action='default'):
        return self.dispatch(data, action=action)

    def default(self, data):
        return ""


class JSONDictSerializer(DictSerializer):
    """Default JSON request body serialization."""

    def default(self, data):
        return jsonutils.dumps(data)


class XMLDictSerializer(DictSerializer):
    def __init__(self, metadata=None, xmlns=None):
        """
        :param metadata: information needed to deserialize xml into
                         a dictionary.
        :param xmlns: XML namespace to include with serialized xml
        """
        super(XMLDictSerializer, self).__init__()
        self.metadata = metadata or {}
        self.xmlns = xmlns

    def default(self, data):
        # We expect data to contain a single key which is the XML root.
        root_key = data.keys()[0]
        doc = minidom.Document()
        node = self._to_xml_node(doc, self.metadata, root_key, data[root_key])

        return self.to_xml_string(node)

    def to_xml_string(self, node, has_atom=False):
        self._add_xmlns(node, has_atom)
        return node.toxml('UTF-8')

    #NOTE (ameade): the has_atom should be removed after all of the
    # xml serializers and view builders have been updated to the current
    # spec that required all responses include the xmlns:atom, the has_atom
    # flag is to prevent current tests from breaking
    def _add_xmlns(self, node, has_atom=False):
        if self.xmlns is not None:
            node.setAttribute('xmlns', self.xmlns)
        if has_atom:
            node.setAttribute('xmlns:atom', "http://www.w3.org/2005/Atom")

    def _to_xml_node(self, doc, metadata, nodename, data):
        """Recursive method to convert data members to XML nodes."""
        result = doc.createElement(nodename)

        # Set the xml namespace if one is specified
        # TODO(justinsb): We could also use prefixes on the keys
        xmlns = metadata.get('xmlns', None)
        if xmlns:
            result.setAttribute('xmlns', xmlns)

        #TODO(bcwaldon): accomplish this without a type-check
        if isinstance(data, list):
            collections = metadata.get('list_collections', {})
            if nodename in collections:
                metadata = collections[nodename]
                for item in data:
                    node = doc.createElement(metadata['item_name'])
                    node.setAttribute(metadata['item_key'], str(item))
                    result.appendChild(node)
                return result
            singular = metadata.get('plurals', {}).get(nodename, None)
            if singular is None:
                if nodename.endswith('s'):
                    singular = nodename[:-1]
                else:
                    singular = 'item'
            for item in data:
                node = self._to_xml_node(doc, metadata, singular, item)
                result.appendChild(node)
        #TODO(bcwaldon): accomplish this without a type-check
        elif isinstance(data, dict):
            collections = metadata.get('dict_collections', {})
            if nodename in collections:
                metadata = collections[nodename]
                for k, v in data.items():
                    node = doc.createElement(metadata['item_name'])
                    node.setAttribute(metadata['item_key'], str(k))
                    text = doc.createTextNode(str(v))
                    node.appendChild(text)
                    result.appendChild(node)
                return result
            attrs = metadata.get('attributes', {}).get(nodename, {})
            for k, v in data.items():
                if k in attrs:
                    result.setAttribute(k, str(v))
                else:
                    if k == "deleted":
                        v = str(bool(v))
                    node = self._to_xml_node(doc, metadata, k, v)
                    result.appendChild(node)
        else:
            # Type is atom
            node = doc.createTextNode(str(data))
            result.appendChild(node)
        return result

    def _create_link_nodes(self, xml_doc, links):
        link_nodes = []
        for link in links:
            link_node = xml_doc.createElement('atom:link')
            link_node.setAttribute('rel', link['rel'])
            link_node.setAttribute('href', link['href'])
            if 'type' in link:
                link_node.setAttribute('type', link['type'])
            link_nodes.append(link_node)
        return link_nodes

    def _to_xml(self, root):
        """Convert the xml object to an xml string."""
        return etree.tostring(root, encoding='UTF-8', xml_declaration=True)
