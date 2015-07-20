# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 Red Hat, Inc.
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

import sys

from paste import deploy

from trove.common import local


class BasePasteFactory(object):

    """A base class for paste app and filter factories.

    Sub-classes must override the KEY class attribute and provide
    a __call__ method.
    """

    KEY = None

    def __init__(self, data):
        self.data = data

    def _import_factory(self, local_conf):
        """Import an app/filter class.

        Lookup the KEY from the PasteDeploy local conf and import the
        class named there. This class can then be used as an app or
        filter factory.

        Note we support the <module>:<class> format.

        Note also that if you do e.g.

          key =
              value

        then ConfigParser returns a value with a leading newline, so
        we strip() the value before using it.
        """
        mod_str, _sep, class_str = local_conf[self.KEY].strip().rpartition(':')
        del local_conf[self.KEY]

        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)


class AppFactory(BasePasteFactory):

    """A Generic paste.deploy app factory.

    This requires openstack.app_factory to be set to a callable which returns a
    WSGI app when invoked. The format of the name is <module>:<callable> e.g.

      [app:myfooapp]
      paste.app_factory = trove.common.pastedeploy:app_factory
      openstack.app_factory = myapp:Foo

    The WSGI app constructor must accept a data object and a local config
    dict as its two arguments.
    """

    KEY = 'openstack.app_factory'

    def __call__(self, global_conf, **local_conf):
        """The actual paste.app_factory protocol method."""
        factory = self._import_factory(local_conf)
        return factory(self.data, **local_conf)


class FilterFactory(AppFactory):

    """A Generic paste.deploy filter factory.

    This requires openstack.filter_factory to be set to a callable which
    returns a  WSGI filter when invoked. The format is <module>:<callable> e.g.

      [filter:myfoofilter]
      paste.filter_factory = trove.common.pastedeploy:filter_factory
      openstack.filter_factory = myfilter:Foo

    The WSGI filter constructor must accept a WSGI app, a data object and
    a local config dict as its three arguments.
    """

    KEY = 'openstack.filter_factory'

    def __call__(self, global_conf, **local_conf):
        """The actual paste.filter_factory protocol method."""
        factory = self._import_factory(local_conf)

        def filter(app):
            return factory(app, self.data, **local_conf)

        return filter


def app_factory(global_conf, **local_conf):
    """A paste app factory used with paste_deploy_app()."""
    return local.store.app_factory(global_conf, **local_conf)


def filter_factory(global_conf, **local_conf):
    """A paste filter factory used with paste_deploy_app()."""
    return local.store.filter_factory(global_conf, **local_conf)


def paste_deploy_app(paste_config_file, app_name, data):
    """Load a WSGI app from a PasteDeploy configuration.

    Use deploy.loadapp() to load the app from the PasteDeploy configuration,
    ensuring that the supplied data object is passed to the app and filter
    factories defined in this module.

    To use these factories and the data object, the configuration should look
    like this:

      [app:myapp]
      paste.app_factory = trove.common.pastedeploy:app_factory
      openstack.app_factory = myapp:App
      ...
      [filter:myfilter]
      paste.filter_factory = trove.common.pastedeploy:filter_factory
      openstack.filter_factory = myapp:Filter

    and then:

      myapp.py:

        class App(object):
            def __init__(self, data):
                ...

        class Filter(object):
            def __init__(self, app, data):
                ...

    :param paste_config_file: a PasteDeploy config file
    :param app_name: the name of the app/pipeline to load from the file
    :param data: a data object to supply to the app and its filters
    :returns: the WSGI app
    """
    (af, ff) = (AppFactory(data), FilterFactory(data))

    local.store.app_factory = af
    local.store.filter_factory = ff
    try:
        return deploy.loadapp("config:%s" % paste_config_file, name=app_name)
    finally:
        del local.store.app_factory
        del local.store.filter_factory
