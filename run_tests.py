import gettext
import os
import urllib
import sys

from reddwarf.tests.config import CONFIG
from wsgi_intercept.httplib2_intercept import install as wsgi_install
import proboscis
from eventlet import greenthread
import wsgi_intercept



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


def initialize_reddwarf(config_file):
    # The test version of poll_until doesn't utilize LoopingCall.
    import optparse
    from reddwarf.db import db_api
    from reddwarf.common import config as rd_config
    from reddwarf.common import wsgi
    from reddwarf import version


    def create_options(parser):
        parser.add_option('-p', '--port', dest="port", metavar="PORT",
                          type=int, default=9898,
                          help="Port the Reddwarf API host listens on. "
                         "Default: %default")
        rd_config.add_common_options(parser)
        rd_config.add_log_options(parser)

    def usage():
        usage = ""

    oparser = optparse.OptionParser(version="%%prog %s"
        % version.version_string(),
        usage=usage())
    create_options(oparser)
    (options, args) = rd_config.parse_options(oparser, cli_args=[config_file])
    rd_config.Config.load_paste_config('reddwarf', options, args)
    # Modify these values by hand
    rd_config.Config.instance['fake_mode_events'] = 'simulated'
    rd_config.Config.instance['log_file'] = 'rdtest.log'
    conf, app = rd_config.Config.load_paste_app('reddwarf', options, args)
    rd_config.setup_logging(options, conf)
    return conf, app


def initialize_database(rd_conf):
    from reddwarf.db import db_api
    from reddwarf.instance import models
    from reddwarf.db.sqlalchemy import session
    db_api.drop_db(rd_conf)  # Destroys the database, if it exists.
    db_api.db_sync(rd_conf)
    session.configure_db(rd_conf)
    # Adds the image for mysql (needed to make most calls work).
    models.ServiceImage.create(service_name="mysql", image_id="fake")
    db_api.configure_db(rd_conf)


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

    wsgi_intercept.add_wsgi_intercept('localhost', 8779, wsgi_interceptor)

    # Finally, engage in some truly evil monkey business. We want
    # to change anything which spawns threads with eventlet to instead simply
    # put those functions on a queue in memory. Then, we swap out any functions
    # which might try to take a nap to instead call functions that go through
    # this queue and call the functions that would normally run in seperate
    # threads.
    import eventlet
    from reddwarf.tests.fakes.common import event_simulator_sleep
    eventlet.sleep = event_simulator_sleep
    greenthread.sleep = event_simulator_sleep
    import time
    time.sleep = event_simulator_sleep


def replace_poll_until():
    from reddwarf.common import utils as rd_utils
    from reddwarf.tests import util as test_utils
    rd_utils.poll_until = test_utils.poll_until

if __name__=="__main__":
    wsgi_install()
    add_support_for_localization()
    replace_poll_until()
    # Load Reddwarf config file.
    conf, app = initialize_reddwarf("etc/reddwarf/reddwarf.conf.test")
    # Initialize sqlite database.
    initialize_database(conf)
    # Swap out WSGI, httplib, and several sleep functions with test doubles.
    initialize_fakes(app)
    # Initialize the test configuration.
    CONFIG.load_from_file("etc/tests/localhost.test.conf")

    from reddwarf.tests.api import flavors
    from reddwarf.tests.api import versions
    from reddwarf.tests.api import instances
    from reddwarf.tests.api import instances_actions
    from reddwarf.tests.api import instances_delete
    from reddwarf.tests.api import instances_mysql_down
    from reddwarf.tests.api import databases
    from reddwarf.tests.api import root
    from reddwarf.tests.api import users
    from reddwarf.tests.api.mgmt import accounts
    from reddwarf.tests.api.mgmt import admin_required
    from reddwarf.tests.api.mgmt import instances
    from reddwarf.tests.api.mgmt import storage

    proboscis.TestProgram().run_and_exit()
