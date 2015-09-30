# Copyright 2011 OpenStack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#

"""Help utilities for debugging"""

import sys

from oslo_config import cfg
from oslo_log import log as logging


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

__debug_state = None

pydev_debug_opts = [
    cfg.StrOpt("pydev_debug",
               choices=("disabled", "enabled", "auto"),
               default="disabled",
               help="Enable or disable pydev remote debugging. "
                    "If value is 'auto' tries to connect to remote "
                    "debugger server, but in case of error "
                    "continues running with debugging disabled."),

    cfg.StrOpt("pydev_debug_host",
               help="Pydev debug server host (localhost by default)."),

    cfg.IntOpt("pydev_debug_port",
               default=5678,
               min=1, max=65535,
               help="Pydev debug server port (5678 by default)."),

    cfg.StrOpt("pydev_path",
               help="Set path to pydevd library, used if pydevd is "
                    "not found in python sys.path.")
]

CONF.register_opts(pydev_debug_opts)


def setup():
    """
    Analyze configuration for pydev remote debugging and establish
    connection to remote debugger service if needed

    @return: True if remote debugging was enabled successfully,
        otherwise - False
    """

    global __debug_state

    if CONF.pydev_debug == "enabled":
        __debug_state = __setup_remote_pydev_debug(
            pydev_debug_host=CONF.pydev_debug_host,
            pydev_debug_port=CONF.pydev_debug_port,
            pydev_path=CONF.pydev_path)
    elif CONF.pydev_debug == "auto":
        __debug_state = __setup_remote_pydev_debug_safe(
            pydev_debug_host=CONF.pydev_debug_host,
            pydev_debug_port=CONF.pydev_debug_port,
            pydev_path=CONF.pydev_path)
    else:
        __debug_state = False


def enabled():
    """
    @return: True if connection to remote debugger established, otherwise False
    """
    assert __debug_state is not None, ("debug_utils are not initialized. "
                                       "Please call setup() method first")
    return __debug_state


def __setup_remote_pydev_debug_safe(pydev_debug_host=None,
                                    pydev_debug_port=5678, pydev_path=None):
    """
    Safe version of __setup_remote_pydev_debug method. In error case returns
    False as result instead of Exception raising

    @see: __setup_remote_pydev_debug
    """

    try:
        return __setup_remote_pydev_debug(
            pydev_debug_host=pydev_debug_host,
            pydev_debug_port=pydev_debug_port,
            pydev_path=pydev_path)
    except Exception as e:
        LOG.warn(_("Can't connect to remote debug server. Continuing to "
                 "work in standard mode. Error: %s."), e)
        return False


def __setup_remote_pydev_debug(pydev_debug_host=None, pydev_debug_port=None,
                               pydev_path=None):
    """
    Method connects to remote debug server, and attach current thread trace
    to debugger. Also thread.start_new_thread thread.start_new are patched to
    enable debugging of new threads

    @param pydev_debug_host: remote debug server host hame, 'localhost'
        if not specified or None
    @param pydev_debug_port: remote debug server port, 5678
        if not specified or None
    @param pydev_path: optional path to pydevd library, used it pydevd is not
        found in python sys.path
    @return: True if debugging initialized,
        otherwise exception should be raised
    """

    try:
        import pydevd
        LOG.debug("pydevd module was imported from system path")
    except ImportError:
        LOG.debug("Can't load pydevd module from system path. Try loading it "
                  "from pydev_path: %s", pydev_path)
        assert pydev_path, "pydev_path is not set"
        if pydev_path not in sys.path:
            sys.path.append(pydev_path)
        import pydevd
        LOG.debug("pydevd module was imported from pydev_path: %s", pydev_path)
    pydevd.settrace(
        host=pydev_debug_host,
        port=pydev_debug_port,
        stdoutToServer=True,
        stderrToServer=True,
        trace_only_current_thread=False,
        suspend=False,
    )
    return True
