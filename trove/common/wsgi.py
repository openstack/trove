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

import math
import re
import time
import traceback
import uuid

import eventlet.wsgi
import jsonschema
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_service import service
from oslo_utils import encodeutils
import paste.urlmap
import webob
import webob.dec
import webob.exc

from trove.common import base_wsgi
from trove.common import cfg
from trove.common import context as rd_context
from trove.common import exception
from trove.common.i18n import _
from trove.common import pastedeploy
from trove.common import utils

CONTEXT_KEY = 'trove.context'
Router = base_wsgi.Router
Debug = base_wsgi.Debug
Middleware = base_wsgi.Middleware
JSONDictSerializer = base_wsgi.JSONDictSerializer
RequestDeserializer = base_wsgi.RequestDeserializer

CONF = cfg.CONF
# Raise the default from 8192 to accommodate large tokens
eventlet.wsgi.MAX_HEADER_LINE = CONF.max_header_line

eventlet.patcher.monkey_patch(all=False, socket=True)

LOG = logging.getLogger('trove.common.wsgi')


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
    LOG.debug("Trove started on %s", host)
    app = pastedeploy.paste_deploy_app(paste_config_file, app_name, data)
    server = base_wsgi.Service(app, port, host=host,
                               backlog=backlog, threads=threads)
    return service.launch(CONF, server, workers)


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


class Router(base_wsgi.Router):
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


class Request(base_wsgi.Request):
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
            if format in ['json']:
                return 'application/{0}'.format(parts[1])

        ctypes = {
            'application/vnd.openstack.trove+json': "application/json",
            'application/json': "application/json",
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
    """A result whose serialization is compatible with JSON."""

    def __init__(self, data, status=200):
        self._data = data
        self.status = status

    def data(self, serialization_type):
        """Return an appropriate serialized type for the body.
           serialization_type is not used presently, but may be
           in the future, so it stays.
        """

        if hasattr(self._data, "data_for_json"):
            return self._data.data_for_json()
        return self._data


class Resource(base_wsgi.Resource):
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
                "figure out what went wrong: (%s)." % exception_uuid,
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
        # So we override the behavior here so we can at least log it.
        try:
            return super(Resource, self).serialize_response(
                action, action_result, accept)
        except Exception:
            # execute_action either returns the results or a Fault object.
            # If action_result is not a Fault then there really was a
            # serialization error which we log. Otherwise return the Fault.
            if not isinstance(action_result, Fault):
                LOG.exception("Unserializable result detected.")
                raise
            return action_result


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
        webob.exc.HTTPForbidden: [
            exception.ReplicaSourceDeleteForbidden,
            exception.BackupTooLarge,
            exception.ModuleAccessForbidden,
            exception.ModuleAppliedToInstance,
            exception.PolicyNotAuthorized,
            exception.LogAccessForbidden,
        ],
        webob.exc.HTTPBadRequest: [
            exception.InvalidModelError,
            exception.BadRequest,
            exception.CannotResizeToSameSize,
            exception.BadValue,
            exception.DatabaseAlreadyExists,
            exception.UserAlreadyExists,
            exception.LocalStorageNotSpecified,
            exception.ModuleAlreadyExists,
        ],
        webob.exc.HTTPNotFound: [
            exception.NotFound,
            exception.ComputeInstanceNotFound,
            exception.ModelNotFoundError,
            exception.UserNotFound,
            exception.DatabaseNotFound,
            exception.QuotaResourceUnknown,
            exception.BackupFileNotFound,
            exception.ClusterNotFound,
            exception.DatastoreNotFound,
            exception.SwiftNotFound,
            exception.ModuleTypeNotFound,
            exception.RootHistoryNotFound,
        ],
        webob.exc.HTTPConflict: [
            exception.BackupNotCompleteError,
            exception.RestoreBackupIntegrityError,
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
            exception.LocalStorageNotSupported,
            exception.DatastoreOperationNotSupported,
            exception.ClusterInstanceOperationNotSupported,
            exception.ClusterDatastoreNotSupported
        ],
    }

    schemas = {}

    @classmethod
    def get_schema(cls, action, body):
        LOG.debug("Getting schema for %(name)s:%(action)s",
                  {'name': cls.__class__.__name__, 'action': action})
        if cls.schemas:
            matching_schema = cls.schemas.get(action, {})
            if matching_schema:
                LOG.debug("Found Schema: %s",
                          matching_schema.get("name", matching_schema))
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
        return Resource(
            self,
            RequestDeserializer(),
            TroveResponseSerializer(),
            self.exception_map)

    def _extract_limits(self, params):
        return {key: params[key] for key in params.keys()
                if key in ["limit", "marker"]}


class TroveResponseSerializer(base_wsgi.ResponseSerializer):
    def serialize_body(self, response, data, content_type, action):
        """Overrides body serialization in base_wsgi.ResponseSerializer.

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
        403: webob.exc.HTTPForbidden,
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

        content_type = req.best_match_content_type()
        serializer = {
            'application/json': base_wsgi.JSONDictSerializer(),
        }[content_type]

        self.wrapped_exc.body = serializer.serialize(fault_data, content_type)
        self.wrapped_exc.content_type = content_type
        return self.wrapped_exc


class ContextMiddleware(base_wsgi.Middleware):
    def __init__(self, application):
        self.admin_roles = CONF.admin_roles
        super(ContextMiddleware, self).__init__(application)

    def _extract_limits(self, params):
        return {key: params[key] for key in params.keys()
                if key in ["limit", "marker"]}

    def process_request(self, request):
        service_catalog = None
        catalog_header = request.headers.get('X-Service-Catalog', None)
        if catalog_header:
            try:
                service_catalog = jsonutils.loads(catalog_header)
            except ValueError:
                raise webob.exc.HTTPInternalServerError(
                    _('Invalid service catalog json.'))
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
                                          marker=limits.get('marker'),
                                          service_catalog=service_catalog,
                                          roles=roles)
        request.environ[CONTEXT_KEY] = context

    @classmethod
    def factory(cls, global_config, **local_config):
        def _factory(app):
            LOG.debug("Created context middleware with config: %s",
                      local_config)
            return cls(app)

        return _factory


class FaultWrapper(base_wsgi.Middleware):
    """Calls down the middleware stack, making exceptions into faults."""

    @webob.dec.wsgify(RequestClass=base_wsgi.Request)
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
            LOG.exception("Caught error: %s.",
                          encodeutils.exception_to_unicode(ex))
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

        serializer = {'application/json': JSONDictSerializer(),
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
        return jsonutils.dump_as_bytes(data)
