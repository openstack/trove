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

import functools
import gettext
import os
import sys
import traceback

import eventlet
from oslo_log import log as logging
import proboscis
import six
from six.moves import urllib
import wsgi_intercept
from wsgi_intercept.httplib2_intercept import install as wsgi_install

from trove.common import cfg
from trove.common.rpc import service as rpc_service
from trove.common.rpc import version as rpc_version
from trove.common import utils
from trove import rpc
from trove.tests.config import CONFIG
from trove.tests import root_logger

eventlet.monkey_patch(thread=False)

CONF = cfg.CONF
original_excepthook = sys.excepthook


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

    if six.PY3:
        gettext.install('nova')
    else:
        gettext.install('nova', unicode=True)


def initialize_trove(config_file):
    from trove.common import pastedeploy

    root_logger.DefaultRootLogger()

    cfg.CONF(args=[],
             project='trove',
             default_config_files=[config_file])
    logging.setup(CONF, None)
    topic = CONF.taskmanager_queue
    rpc.init(CONF)

    taskman_service = rpc_service.RpcService(
        CONF.taskmanager_rpc_encr_key, topic=topic,
        rpc_api_version=rpc_version.RPC_API_VERSION,
        manager='trove.taskmanager.manager.Manager')
    taskman_service.start()

    return pastedeploy.paste_deploy_app(config_file, 'trove', {})


def datastore_init():
    # Adds the datastore for mysql (needed to make most calls work).
    from trove.configuration.models import DatastoreConfigurationParameters
    from trove.datastore import models

    models.DBDatastore.create(
        id=CONFIG.dbaas_datastore_id, name=CONFIG.dbaas_datastore,
        default_version_id=CONFIG.dbaas_datastore_version_id)

    models.DBDatastore.create(id=utils.generate_uuid(),
                              name=CONFIG.dbaas_datastore_name_no_versions,
                              default_version_id=None)

    main_dsv = models.DBDatastoreVersion.create(
        id=CONFIG.dbaas_datastore_version_id,
        datastore_id=CONFIG.dbaas_datastore_id,
        name=CONFIG.dbaas_datastore_version,
        manager="mysql",
        image_id='c00000c0-00c0-0c00-00c0-000c000000cc',
        packages='test packages',
        active=1)
    models.DBDatastoreVersion.create(
        id="d00000d0-00d0-0d00-00d0-000d000000dd",
        datastore_id=CONFIG.dbaas_datastore_id,
        name='mysql_inactive_version', manager="mysql",
        image_id='c00000c0-00c0-0c00-00c0-000c000000cc',
        packages=None, active=0)

    def add_parm(name, data_type, max_size, min_size=0, restart_required=0):
        DatastoreConfigurationParameters.create(
            datastore_version_id=main_dsv.id,
            name=name,
            restart_required=restart_required,
            max_size=max_size,
            min_size=0,
            data_type=data_type,
            deleted=0,
            deleted_at=None)

    add_parm('key_buffer_size', 'integer', 4294967296)
    add_parm('connect_timeout', 'integer', 65535)
    add_parm('join_buffer_size', 'integer', 4294967296)
    add_parm('local_infile', 'integer', 1)
    add_parm('collation_server', 'string', None, None)
    add_parm('innodb_buffer_pool_size', 'integer', 57671680,
             restart_required=1)


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
                env['PATH_INFO'] = urllib.parse.unquote(path_info)
            return app.__call__(env, start_response)

        return call_back

    wsgi_intercept.add_wsgi_intercept('localhost',
                                      CONF.bind_port,
                                      wsgi_interceptor)
    from trove.tests.util import event_simulator
    event_simulator.monkey_patch()
    from trove.tests.fakes import taskmanager
    taskmanager.monkey_patch()


def parse_args_for_test_config():
    test_conf = 'etc/tests/localhost.test.conf'
    repl = False
    new_argv = []
    for index in range(len(sys.argv)):
        arg = sys.argv[index]
        print(arg)
        if arg[:14] == "--test-config=":
            test_conf = arg[14:]
        elif arg == "--repl":
            repl = True
        else:
            new_argv.append(arg)
    sys.argv = new_argv
    return test_conf, repl


def run_tests(repl):
    """Runs all of the tests."""

    if repl:
        # Actually show errors in the repl.
        sys.excepthook = original_excepthook

        def no_thanks(exit_code):
            print("Tests finished with exit code %d." % exit_code)
        sys.exit = no_thanks

    proboscis.TestProgram().run_and_exit()

    if repl:
        import code
        code.interact()


def import_tests():
    # F401 unused imports needed for tox tests
    from trove.tests.api import backups  # noqa
    from trove.tests.api import configurations  # noqa
    from trove.tests.api import databases  # noqa
    from trove.tests.api import datastores  # noqa
    from trove.tests.api import instances as rd_instances  # noqa
    from trove.tests.api import instances_actions as rd_actions  # noqa
    from trove.tests.api import instances_delete  # noqa
    from trove.tests.api import instances_resize  # noqa
    from trove.tests.api import limits  # noqa
    from trove.tests.api.mgmt import instances_actions as mgmt_actions  # noqa
    from trove.tests.api import replication  # noqa
    from trove.tests.api import root  # noqa
    from trove.tests.api import user_access  # noqa
    from trove.tests.api import users  # noqa
    from trove.tests.api import versions  # noqa
    from trove.tests.db import migrations  # noqa


def main(import_func):
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
        # Swap out WSGI, httplib, and other components with test doubles.
        initialize_fakes(app)

        # Initialize the test configuration.
        test_config_file, repl = parse_args_for_test_config()
        CONFIG.load_from_file(test_config_file)

        import_func()

        from trove.tests.util import event_simulator
        event_simulator.run_main(functools.partial(run_tests, repl))

    except Exception as e:
        # Printing the error manually like this is necessary due to oddities
        # with sys.excepthook.
        print("Run tests failed: %s" % e)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main(import_tests)
