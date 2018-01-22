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

import abc

from lxml import etree
from oslo_log import log as logging
from oslo_utils import encodeutils
import routes
import six
import stevedore
import webob.dec
import webob.exc

from trove.common import base_exception as exception
from trove.common import base_wsgi
from trove.common.i18n import _
from trove.common import wsgi

LOG = logging.getLogger(__name__)
DEFAULT_XMLNS = "http://docs.openstack.org/trove"
XMLNS_ATOM = "http://www.w3.org/2005/Atom"


@six.add_metaclass(abc.ABCMeta)
class ExtensionDescriptor(object):
    """Base class that defines the contract for extensions.

    Note that you don't have to derive from this class to have a valid
    extension; it is purely a convenience.

    """
    @abc.abstractmethod
    def get_name(self):
        """The name of the extension.

        e.g. 'Fox In Socks'

        """
        pass

    @abc.abstractmethod
    def get_alias(self):
        """The alias for the extension.

        e.g. 'FOXNSOX'

        """
        pass

    @abc.abstractmethod
    def get_description(self):
        """Friendly description for the extension.

        e.g. 'The Fox In Socks Extension'

        """
        pass

    @abc.abstractmethod
    def get_namespace(self):
        """The XML namespace for the extension.

        e.g. 'http://www.fox.in.socks/api/ext/pie/v1.0'

        """
        pass

    @abc.abstractmethod
    def get_updated(self):
        """The timestamp when the extension was last updated.

        e.g. '2011-01-22T13:25:27-06:00'

        """
        pass

    def get_resources(self):
        """List of extensions.ResourceExtension extension objects.

        Resources define new nouns, and are accessible through URLs.

        """
        resources = []
        return resources

    def get_actions(self):
        """List of extensions.ActionExtension extension objects.

        Actions are verbs callable from the API.

        """
        actions = []
        return actions

    def get_request_extensions(self):
        """List of extensions.RequestException extension objects.

        Request extensions are used to handle custom request data.

        """
        request_exts = []
        return request_exts


class ActionExtensionController(object):
    def __init__(self, application):
        self.application = application
        self.action_handlers = {}

    def add_action(self, action_name, handler):
        self.action_handlers[action_name] = handler

    def action(self, req, id, body):
        for action_name, handler in self.action_handlers.items():
            if action_name in body:
                return handler(body, req, id)
        # no action handler found (bump to downstream application)
        res = self.application
        return res


class ActionExtensionResource(wsgi.Resource):

    def __init__(self, application):
        controller = ActionExtensionController(application)
        wsgi.Resource.__init__(self, controller)

    def add_action(self, action_name, handler):
        self.controller.add_action(action_name, handler)


class RequestExtensionController(object):

    def __init__(self, application):
        self.application = application
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def process(self, req, *args, **kwargs):
        res = req.get_response(self.application)
        # currently request handlers are un-ordered
        for handler in self.handlers:
            res = handler(req, res)
        return res


class RequestExtensionResource(wsgi.Resource):

    def __init__(self, application):
        controller = RequestExtensionController(application)
        wsgi.Resource.__init__(self, controller)

    def add_handler(self, handler):
        self.controller.add_handler(handler)


class ExtensionsResource(wsgi.Resource):

    def __init__(self, extension_manager):
        self.extension_manager = extension_manager
        body_serializers = {'application/xml': ExtensionsXMLSerializer()}
        serializer = base_wsgi.ResponseSerializer(
            body_serializers=body_serializers)
        super(ExtensionsResource, self).__init__(self, None, serializer)

    def _translate(self, ext):
        ext_data = {}
        ext_data['name'] = ext.get_name()
        ext_data['alias'] = ext.get_alias()
        ext_data['description'] = ext.get_description()
        ext_data['namespace'] = ext.get_namespace()
        ext_data['updated'] = ext.get_updated()
        ext_data['links'] = []
        return ext_data

    def index(self, req):
        extensions = []
        for _alias, ext in self.extension_manager.extensions.items():
            extensions.append(self._translate(ext))
        return dict(extensions=extensions)

    def show(self, req, id):
        # NOTE(dprince): the extensions alias is used as the 'id' for show
        ext = self.extension_manager.extensions.get(id, None)
        if not ext:
            raise webob.exc.HTTPNotFound(
                _("Extension with alias %s does not exist") % id)

        return dict(extension=self._translate(ext))

    def delete(self, req, id):
        raise webob.exc.HTTPNotFound()

    def create(self, req):
        raise webob.exc.HTTPNotFound()


class ExtensionMiddleware(wsgi.Middleware):
    """Extensions middleware for WSGI."""

    @classmethod
    def factory(cls, global_config, **local_config):
        """Paste factory."""
        def _factory(app):
            return cls(app, global_config, **local_config)
        return _factory

    def _action_ext_resources(self, application, ext_mgr, mapper):
        """Return a dict of ActionExtensionResource-s by collection."""
        action_resources = {}
        for action in ext_mgr.get_actions():
            if action.collection not in action_resources.keys():
                resource = ActionExtensionResource(application)
                mapper.connect("/%s/:(id)/action.:(format)" %
                               action.collection,
                               action='action',
                               controller=resource,
                               conditions=dict(method=['POST']))
                mapper.connect("/%s/:(id)/action" %
                               action.collection,
                               action='action',
                               controller=resource,
                               conditions=dict(method=['POST']))
                action_resources[action.collection] = resource

        return action_resources

    def _request_ext_resources(self, application, ext_mgr, mapper):
        """Returns a dict of RequestExtensionResource-s by collection."""
        request_ext_resources = {}
        for req_ext in ext_mgr.get_request_extensions():
            if req_ext.key not in request_ext_resources.keys():
                resource = RequestExtensionResource(application)
                mapper.connect(req_ext.url_route + '.:(format)',
                               action='process',
                               controller=resource,
                               conditions=req_ext.conditions)

                mapper.connect(req_ext.url_route,
                               action='process',
                               controller=resource,
                               conditions=req_ext.conditions)
                request_ext_resources[req_ext.key] = resource

        return request_ext_resources

    def __init__(self, application, config, ext_mgr=None):
        ext_mgr = (ext_mgr or
                   ExtensionManager())
        mapper = routes.Mapper()

        # extended resources
        for resource_ext in ext_mgr.get_resources():
            LOG.debug('Extended resource: %s', resource_ext.collection)
            controller_resource = wsgi.Resource(resource_ext.controller,
                                                resource_ext.deserializer,
                                                resource_ext.serializer)
            self._map_custom_collection_actions(resource_ext, mapper,
                                                controller_resource)
            kargs = dict(controller=controller_resource,
                         collection=resource_ext.collection_actions,
                         member=resource_ext.member_actions)
            if resource_ext.parent:
                kargs['parent_resource'] = resource_ext.parent
            mapper.resource(resource_ext.collection,
                            resource_ext.collection, **kargs)

        # extended actions
        action_resources = self._action_ext_resources(application, ext_mgr,
                                                      mapper)
        for action in ext_mgr.get_actions():
            LOG.debug('Extended action: %s', action.action_name)
            resource = action_resources[action.collection]
            resource.add_action(action.action_name, action.handler)

        # extended requests
        req_controllers = self._request_ext_resources(application, ext_mgr,
                                                      mapper)
        for request_ext in ext_mgr.get_request_extensions():
            LOG.debug('Extended request: %s', request_ext.key)
            controller = req_controllers[request_ext.key]
            controller.add_handler(request_ext.handler)

        self._router = routes.middleware.RoutesMiddleware(self._dispatch,
                                                          mapper)

        super(ExtensionMiddleware, self).__init__(application)

    def _map_custom_collection_actions(self, resource_ext, mapper,
                                       controller_resource):
        for action, method in resource_ext.collection_actions.items():
            parent = resource_ext.parent
            conditions = dict(method=[method])
            path = "/%s/%s" % (resource_ext.collection, action)

            path_prefix = ""
            if parent:
                path_prefix = "/%s/{%s_id}" % (parent["collection_name"],
                                               parent["member_name"])

            with mapper.submapper(controller=controller_resource,
                                  action=action,
                                  path_prefix=path_prefix,
                                  conditions=conditions) as submap:
                submap.connect(path_prefix + path, path)
                submap.connect(path_prefix + path + "_format",
                               "%s.:(format)" % path)

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        """Route the incoming request with router."""
        req.environ['extended.app'] = self.application
        return self._router

    @staticmethod
    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def _dispatch(req):
        """Dispatch the request.

        Returns the routed WSGI app's response or defers to the extended
        application.

        """
        match = req.environ['wsgiorg.routing_args'][1]
        if not match:
            return req.environ['extended.app']
        app = match['controller']
        return app


class ExtensionManager(object):

    EXT_NAMESPACE = 'trove.api.extensions'

    def __init__(self):
        LOG.debug('Initializing extension manager.')

        self.extensions = {}
        self._load_all_extensions()

    def get_resources(self):
        """Returns a list of ResourceExtension objects."""
        resources = []
        extension_resource = ExtensionsResource(self)
        res_ext = ResourceExtension('extensions',
                                    extension_resource,
                                    serializer=extension_resource.serializer)
        resources.append(res_ext)
        for alias, ext in self.extensions.items():
            try:
                resources.extend(ext.get_resources())
            except AttributeError:
                pass
        return resources

    def get_actions(self):
        """Returns a list of ActionExtension objects."""
        actions = []
        for alias, ext in self.extensions.items():
            try:
                actions.extend(ext.get_actions())
            except AttributeError:
                pass
        return actions

    def get_request_extensions(self):
        """Returns a list of RequestExtension objects."""
        request_exts = []
        for alias, ext in self.extensions.items():
            try:
                request_exts.extend(ext.get_request_extensions())
            except AttributeError:
                pass
        return request_exts

    def _check_extension(self, extension):
        """Checks for required methods in extension objects."""
        try:
            LOG.debug('Ext name: %s', extension.get_name())
            LOG.debug('Ext alias: %s', extension.get_alias())
            LOG.debug('Ext description: %s', extension.get_description())
            LOG.debug('Ext namespace: %s', extension.get_namespace())
            LOG.debug('Ext updated: %s', extension.get_updated())
        except AttributeError as ex:
            LOG.exception("Exception loading extension: %s",
                          encodeutils.exception_to_unicode(ex))
            return False
        return True

    def _check_load_extension(self, ext):
        LOG.debug('Ext: %s', ext.obj)
        return isinstance(ext.obj, ExtensionDescriptor)

    def _load_all_extensions(self):
        self.api_extension_manager = stevedore.enabled.EnabledExtensionManager(
            namespace=self.EXT_NAMESPACE,
            check_func=self._check_load_extension,
            invoke_on_load=True,
            invoke_kwds={})
        self.api_extension_manager.map(self.add_extension)

    def add_extension(self, ext):
        ext = ext.obj
        # Do nothing if the extension doesn't check out
        if not self._check_extension(ext):
            return

        alias = ext.get_alias()
        LOG.debug('Loaded extension: %s', alias)

        if alias in self.extensions:
            raise exception.Error("Found duplicate extension: %s" % alias)
        self.extensions[alias] = ext


class RequestExtension(object):

    def __init__(self, method, url_route, handler):
        self.url_route = url_route
        self.handler = handler
        self.conditions = dict(method=[method])
        self.key = "%s-%s" % (method, url_route)


class ActionExtension(object):

    def __init__(self, collection, action_name, handler):
        self.collection = collection
        self.action_name = action_name
        self.handler = handler


class BaseResourceExtension(object):

    def __init__(self, collection, controller, parent=None,
                 collection_actions=None, member_actions=None,
                 deserializer=None, serializer=None):
        if not collection_actions:
            collection_actions = {}
        if not member_actions:
            member_actions = {}
        self.collection = collection
        self.controller = controller
        self.parent = parent
        self.collection_actions = collection_actions
        self.member_actions = member_actions
        self.deserializer = deserializer
        self.serializer = serializer


class ExtensionsXMLSerializer(base_wsgi.XMLDictSerializer):

    def __init__(self):
        self.nsmap = {None: DEFAULT_XMLNS, 'atom': XMLNS_ATOM}

    def show(self, ext_dict):
        ext = etree.Element('extension', nsmap=self.nsmap)
        self._populate_ext(ext, ext_dict['extension'])
        return self._to_xml(ext)

    def index(self, exts_dict):
        exts = etree.Element('extensions', nsmap=self.nsmap)
        for ext_dict in exts_dict['extensions']:
            ext = etree.SubElement(exts, 'extension')
            self._populate_ext(ext, ext_dict)
        return self._to_xml(exts)

    def _populate_ext(self, ext_elem, ext_dict):
        """Populate an extension xml element from a dict."""

        ext_elem.set('name', ext_dict['name'])
        ext_elem.set('namespace', ext_dict['namespace'])
        ext_elem.set('alias', ext_dict['alias'])
        ext_elem.set('updated', ext_dict['updated'])
        desc = etree.Element('description')
        desc.text = ext_dict['description']
        ext_elem.append(desc)
        for link in ext_dict.get('links', []):
            elem = etree.SubElement(ext_elem, '{%s}link' % XMLNS_ATOM)
            elem.set('rel', link['rel'])
            elem.set('href', link['href'])
            elem.set('type', link['type'])
        return ext_elem

    def _to_xml(self, root):
        """Convert the xml object to an xml string."""

        return etree.tostring(root, encoding='UTF-8')


class ResourceExtension(BaseResourceExtension):
    def __init__(self, collection, controller, parent=None,
                 collection_actions=None, member_actions=None,
                 deserializer=None, serializer=None):
        super(ResourceExtension, self).__init__(
            collection, controller,
            parent=parent,
            collection_actions=collection_actions,
            member_actions=member_actions,
            deserializer=wsgi.RequestDeserializer(),
            serializer=wsgi.TroveResponseSerializer())


class TroveExtensionMiddleware(ExtensionMiddleware):

    def __init__(self, application, ext_mgr=None):
        ext_mgr = (ext_mgr or
                   ExtensionManager())
        mapper = routes.Mapper()

        # extended resources
        for resource_ext in ext_mgr.get_resources():
            LOG.debug('Extended resource: %s', resource_ext.collection)
            # The only difference here is that we are using our common
            # wsgi.Resource instead of the openstack common wsgi.Resource
            exception_map = None
            if hasattr(resource_ext.controller, 'exception_map'):
                exception_map = resource_ext.controller.exception_map
            controller_resource = wsgi.Resource(resource_ext.controller,
                                                resource_ext.deserializer,
                                                resource_ext.serializer,
                                                exception_map)

            self._map_custom_collection_actions(resource_ext, mapper,
                                                controller_resource)
            kargs = dict(controller=controller_resource,
                         collection=resource_ext.collection_actions,
                         member=resource_ext.member_actions)
            if resource_ext.parent:
                kargs['parent_resource'] = resource_ext.parent
            mapper.resource(resource_ext.collection,
                            resource_ext.collection, **kargs)

            mapper.connect(("/%s/{id}" % resource_ext.collection),
                           controller=controller_resource,
                           action='edit',
                           conditions={'method': ['PATCH']})

        # extended actions
        action_resources = self._action_ext_resources(application, ext_mgr,
                                                      mapper)
        for action in ext_mgr.get_actions():
            LOG.debug('Extended action: %s', action.action_name)
            resource = action_resources[action.collection]
            resource.add_action(action.action_name, action.handler)

        # extended requests
        req_controllers = self._request_ext_resources(application, ext_mgr,
                                                      mapper)
        for request_ext in ext_mgr.get_request_extensions():
            LOG.debug('Extended request: %s', request_ext.key)
            controller = req_controllers[request_ext.key]
            controller.add_handler(request_ext.handler)

        self._router = routes.middleware.RoutesMiddleware(self._dispatch,
                                                          mapper)

        super(ExtensionMiddleware, self).__init__(application)


def factory(global_config, **local_config):
    """Paste factory."""
    def _factory(app):
        ext_mgr = ExtensionManager()
        return TroveExtensionMiddleware(app, ext_mgr)
    return _factory
