# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#

import gettext
import os
import urllib
import sys
import traceback

from trove.common import cfg
from trove.openstack.common import log as logging
from trove.tests.config import CONFIG
from wsgi_intercept.httplib2_intercept import install as wsgi_install
import proboscis
import wsgi_intercept
from trove.openstack.common.rpc import service as rpc_service

import eventlet
eventlet.monkey_patch(thread=False)

CONF = cfg.CONF


def add_support_for_localization():
    """Adds support for localization in the logging.

    If ../nova/__init__.py exists, add ../ to Python search path, so that
    it will override what happens to be installed in
    /usr/(local/)lib/python...

    """
    path = os.path.join(os.path.abspath(sys.argv[0]), os.pardir, os.pardir)
    possible_topdir = os.path.normpath(path)
    if os.path.exists(os.path.join(possible_topdir, 'nova', '__init__.py')):
        sys.path.insert(0, possible_topdir)

    gettext.install('nova', unicode=1)


def initialize_trove(config_file):
    from trove.openstack.common import pastedeploy

    cfg.CONF(args=[],
             project='trove',
             default_config_files=[config_file])
    logging.setup(None)
    topic = CONF.taskmanager_queue

    from trove.taskmanager import manager
    manager_impl = manager.Manager()
    taskman_service = rpc_service.Service(None, topic=topic,
                                          manager=manager_impl)
    taskman_service.start()

    return pastedeploy.paste_deploy_app(config_file, 'trove', {})


def datastore_init():
    # Adds the datastore for mysql (needed to make most calls work).
    from trove.datastore import models

    models.DBDatastore.create(id=CONFIG.dbaas_datastore_id,
                              name=CONFIG.dbaas_datastore,
                              default_version_id=
                              CONFIG.dbaas_datastore_version_id)
    models.DBDatastore.create(id="e00000e0-00e0-0e00-00e0-000e000000ee",
                              name='Test_Datastore_1',
                              default_version_id=None)

    models.DBDatastoreVersion.create(id=CONFIG.dbaas_datastore_version_id,
                                     datastore_id=
                                     CONFIG.dbaas_datastore_id,
                                     name=CONFIG.dbaas_datastore_version,
                                     manager="mysql",
                                     image_id=
                                     'c00000c0-00c0-0c00-00c0-000c000000cc',
                                     packages='test packages',
                                     active=1)
    models.DBDatastoreVersion.create(id="d00000d0-00d0-0d00-00d0-000d000000dd",
                                     datastore_id=
                                     CONFIG.dbaas_datastore_id,
                                     name='mysql_inactive_version',
                                     manager="mysql",
                                     image_id=
                                     'c00000c0-00c0-0c00-00c0-000c000000cc',
                                     packages=None, active=0)


def initialize_database():
    from trove.db import get_db_api
    from trove.db.sqlalchemy import session
    db_api = get_db_api()
    db_api.drop_db(CONF)  # Destroys the database, if it exists.
    db_api.db_sync(CONF)
    session.configure_db(CONF)
    datastore_init()
    db_api.configure_db(CONF)


def initialize_fakes(app):
    # Set up WSGI interceptor. This sets up a fake host that responds each
    # time httplib tries to communicate to localhost, port 8779.
    def wsgi_interceptor(*args, **kwargs):

        def call_back(env, start_response):
            path_info = env.get('PATH_INFO')
            if path_info:
                env['PATH_INFO'] = urllib.unquote(path_info)
            #print("%s %s" % (args, kwargs))
            return app.__call__(env, start_response)

        return call_back

    wsgi_intercept.add_wsgi_intercept('localhost',
                                      CONF.bind_port,
                                      wsgi_interceptor)
    from trove.tests.util import event_simulator
    event_simulator.monkey_patch()


def parse_args_for_test_config():
    for index in range(len(sys.argv)):
        arg = sys.argv[index]
        print(arg)
        if arg[:14] == "--test-config=":
            del sys.argv[index]
            return arg[14:]
    return 'etc/tests/localhost.test.conf'

if __name__ == "__main__":
    try:
        wsgi_install()
        add_support_for_localization()
        # Load Trove app
        # Paste file needs absolute path
        config_file = os.path.realpath('etc/trove/trove.conf.test')
        # 'etc/trove/test-api-paste.ini'
        app = initialize_trove(config_file)
        # Initialize sqlite database.
        initialize_database()
        # Swap out WSGI, httplib, and several sleep functions
        # with test doubles.
        initialize_fakes(app)

        # Initialize the test configuration.
        test_config_file = parse_args_for_test_config()
        CONFIG.load_from_file(test_config_file)

        # F401 unused imports needed for tox tests
        from trove.tests.api import backups  # noqa
        from trove.tests.api import header  # noqa
        from trove.tests.api import limits  # noqa
        from trove.tests.api import flavors  # noqa
        from trove.tests.api import versions  # noqa
        from trove.tests.api import instances as rd_instances  # noqa
        from trove.tests.api import instances_actions as rd_actions  # noqa
        from trove.tests.api import instances_delete  # noqa
        from trove.tests.api import instances_mysql_down  # noqa
        from trove.tests.api import instances_resize  # noqa
        from trove.tests.api import databases  # noqa
        from trove.tests.api import datastores  # noqa
        from trove.tests.api import root  # noqa
        from trove.tests.api import root_on_create  # noqa
        from trove.tests.api import users  # noqa
        from trove.tests.api import user_access  # noqa
        from trove.tests.api.mgmt import accounts  # noqa
        from trove.tests.api.mgmt import admin_required  # noqa
        from trove.tests.api.mgmt import hosts  # noqa
        from trove.tests.api.mgmt import instances as mgmt_instances  # noqa
        from trove.tests.api.mgmt import instances_actions as mgmt_actions  # noqa
        from trove.tests.api.mgmt import storage  # noqa
        from trove.tests.api.mgmt import malformed_json  # noqa
    except Exception as e:
        print("Run tests failed: %s" % e)
        traceback.print_exc()
        raise

    proboscis.TestProgram().run_and_exit()
