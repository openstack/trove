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

"""STOLEN FROM NOVA."""

import functools
import inspect
import os
import logging
import socket
import traceback
import weakref

import eventlet
import greenlet
from eventlet import greenthread

from reddwarf.common import config
from reddwarf.openstack.common import rpc
from reddwarf.common import utils
from reddwarf import version

LOG = logging.getLogger(__name__)


class Launcher(object):
    """Launch one or more services and wait for them to complete."""

    def __init__(self):
        """Initialize the service launcher."""
        self._services = []

    @staticmethod
    def run_server(server):
        """Start and wait for a server to finish."""

        server.start()
        server.wait()

    def launch_server(self, server):
        """Load and start the given server."""
        gt = eventlet.spawn(self.run_server, server)
        self._services.append(gt)

    def stop(self):
        """Stop all services which are currently running."""
        for service in self._services:
            service.kill()

    def wait(self):
        """Waits until all services have been stopped, and then returns."""
        for service in self._services:
            try:
                service.wait()
            except greenlet.GreenletExit:
                LOG.error(_("greenthread exited"))
                pass


class Service(object):
    """Generic code to start services and get them listening on rpc"""

    def __init__(self, host, binary, topic, manager, report_interval=None,
                 periodic_interval=None, *args, **kwargs):
        if not host:
            host = socket.gethostname()
        self.host = host
        self.binary = binary
        self.topic = topic
        self.manager_class_name = manager
        manager_class = utils.import_class(self.manager_class_name)
        self.manager = manager_class(host=self.host, *args, **kwargs)
        self.report_interval = report_interval
        self.periodic_interval = periodic_interval
        super(Service, self).__init__(*args, **kwargs)
        self.saved_args, self.saved_kwargs = args, kwargs
        self.timers = []

    def dispatch(self, ctxt, version, method, **kwargs):
        """Handles incoming RPC messages."""
        #TODO(tim.simpson): Maybe in the future actually account for the
        #                   version somehow with multiple managers or by
        #                   sending the manager in or something.
        if not version:
            version = '1.0'

        if version != self.manager.RPC_API_VERSION:
            raise UnsupportedRpcVersion(version=version)

        return self.manager.wrapper(method, ctxt, **kwargs)

    def periodic_tasks(self, raise_on_error=False):
        """Tasks to be run at a periodic interval."""
        self.manager.periodic_tasks(raise_on_error=raise_on_error)

    def report_state(self):
        pass

    def start(self):
        vcs_string = version.version_string_with_vcs()
        LOG.info(_('Starting %(topic)s node (version %(vcs_string)s)'),
                 {'topic': self.topic, 'vcs_string': vcs_string})

        self.conn = rpc.create_connection(new=True)
        LOG.debug(_("Creating Consumer connection for Service %s") %
                  self.topic)

        # Share this same connection for these Consumers
        self.conn.create_consumer(self.topic, self, fanout=False)

        node_topic = '%s.%s' % (self.topic, self.host)
        self.conn.create_consumer(node_topic, self, fanout=False)

        self.conn.create_consumer(self.topic, self, fanout=True)

        # Consume from all consumers in a thread
        self.conn.consume_in_thread()
        if self.report_interval:
            pulse = utils.LoopingCall(self.report_state)
            pulse.start(interval=self.report_interval, now=False)
            self.timers.append(pulse)

        if self.periodic_interval:
            periodic = utils.LoopingCall(self.periodic_tasks)
            periodic.start(interval=self.periodic_interval, now=False)
            self.timers.append(periodic)

    def wait(self):
        for x in self.timers:
            try:
                x.wait()
            except Exception:
                pass

    @classmethod
    def create(cls, host=None, binary=None, topic=None, manager=None,
               report_interval=None, periodic_interval=None):
        """Instantiates class and passes back application object.

        :param host: defaults to FLAGS.host
        :param binary: defaults to basename of executable
        :param topic: defaults to bin_name - 'nova-' part
        :param manager: defaults to FLAGS.<topic>_manager
        :param report_interval: defaults to FLAGS.report_interval
        :param periodic_interval: defaults to FLAGS.periodic_interval

        """
        if not host:
            host = config.Config.get('host')
        if not binary:
            binary = os.path.basename(inspect.stack()[-1][1])
        if not topic:
            topic = binary.rpartition('reddwarf-')[2]
        if not manager:
            manager = config.Config.get('%s_manager' % topic, None)
        if not report_interval:
            report_interval = config.Config.get('report_interval', 10)
        if not periodic_interval:
            periodic_interval = config.Config.get('periodic_interval', 60)
        service_obj = cls(host, binary, topic, manager, report_interval,
                          periodic_interval)

        return service_obj


class Manager(object):
    def __init__(self, host=None):
        self.host = host
        self.tasks = weakref.WeakKeyDictionary()
        super(Manager, self).__init__()

    def periodic_tasks(self, raise_on_error=False):
        """Tasks to be run at a periodic interval."""
        LOG.debug("No. of running tasks: %d" % len(self.tasks))

    def init_host(self):
        """Handle initialization if this is a standalone service.

        Child classes should override this method.

        """
        pass

    #TODO(tim.simpson): Rename this to "execute" or something clearer.
    def wrapper(self, method, context, *args, **kwargs):
        """Maps the respective manager method with a task counter."""
        # TODO(rnirmal): Just adding a basic counter. Will revist and
        # re-implement when we have actual tasks.
        self.tasks[greenthread.getcurrent()] = context
        try:
            if not hasattr(self, method):
                raise AttributeError("No such RPC function '%s'" % method)
            func = getattr(self, method)
            LOG.info(str('*' * 80))
            LOG.info("Running method %s..." % method)
            LOG.info(str('*' * 80))
            result = func(context, *args, **kwargs)
            LOG.info("Finished method %s." % method)
            return result
        except Exception as e:
            LOG.error("Got an error running %s!" % method)
            LOG.error(traceback.format_exc())
        finally:
            LOG.info(str('-' * 80))
            del self.tasks[greenthread.getcurrent()]


_launcher = None


def serve(*servers):
    global _launcher
    if not _launcher:
        _launcher = Launcher()
    for server in servers:
        _launcher.launch_server(server)


def wait():
    try:
        _launcher.wait()
    except KeyboardInterrupt:
        _launcher.stop()
    rpc.cleanup()
