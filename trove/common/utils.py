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
"""I totally stole most of this from melange, thx guys!!!"""

import datetime
import inspect
import jinja2
import time
import six.moves.urllib.parse as urlparse
import uuid
import os
import shutil

from eventlet.timeout import Timeout
from passlib import utils as passlib_utils

from oslo.utils import importutils

from trove.common import cfg
from trove.common import exception
from trove.openstack.common import log as logging
from trove.openstack.common import loopingcall
from trove.openstack.common import processutils
from trove.openstack.common import timeutils
from trove.openstack.common import utils as openstack_utils
from trove.openstack.common.gettextutils import _

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
import_class = importutils.import_class
import_object = importutils.import_object
import_module = importutils.import_module
bool_from_string = openstack_utils.bool_from_string
execute = processutils.execute
isotime = timeutils.isotime

CONF = cfg.CONF
ENV = jinja2.Environment(loader=jinja2.ChoiceLoader([
                         jinja2.FileSystemLoader(CONF.template_path),
                         jinja2.PackageLoader("trove", "templates")
                         ]))


def create_method_args_string(*args, **kwargs):
    """Returns a string representation of args and keyword args.

    I.e. for args=1,2,3 and kwargs={'a':4, 'b':5} you'd get: "1,2,3,a=4,b=5"
    """
    # While %s turns a var into a string but in some rare cases explicit
    # repr() is less likely to raise an exception.
    arg_strs = [repr(arg) for arg in args]
    arg_strs += ['%s=%s' % (repr(key), repr(value))
                 for (key, value) in kwargs.items()]
    return ', '.join(arg_strs)


def stringify_keys(dictionary):
    if dictionary is None:
        return None
    return dict((str(key), value) for key, value in dictionary.iteritems())


def exclude(key_values, *exclude_keys):
    if key_values is None:
        return None
    return dict((key, value) for key, value in key_values.iteritems()
                if key not in exclude_keys)


def generate_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.datetime.utcnow()


def raise_if_process_errored(process, exception):
    try:
        err = process.stderr.read()
        if err:
            raise exception(err)
    except OSError:
        pass


def clean_out(folder):
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))


class cached_property(object):
    """A decorator that converts a function into a lazy property.

    Taken from : https://github.com/nshah/python-memoize
    The function wrapped is called the first time to retrieve the result
    and than that calculated result is used the next time you access
    the value:

        class Foo(object):

            @cached_property
            def bar(self):
                # calculate something important here
                return 42

    """

    def __init__(self, func, name=None, doc=None):
        self.func = func
        self.__name__ = name or func.__name__
        self.__doc__ = doc or func.__doc__

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        value = self.func(obj)
        setattr(obj, self.__name__, value)
        return value


class MethodInspector(object):

    def __init__(self, func):
        self._func = func

    @cached_property
    def required_args(self):
        return self.args[0:self.required_args_count]

    @cached_property
    def optional_args(self):
        keys = self.args[self.required_args_count: len(self.args)]
        return zip(keys, self.defaults)

    @cached_property
    def defaults(self):
        return self.argspec.defaults or ()

    @cached_property
    def required_args_count(self):
        return len(self.args) - len(self.defaults)

    @cached_property
    def args(self):
        args = self.argspec.args
        if inspect.ismethod(self._func):
            args.pop(0)
        return args

    @cached_property
    def argspec(self):
        return inspect.getargspec(self._func)

    def __str__(self):
        optionals = ["[{0}=<{0}>]".format(k) for k, v in self.optional_args]
        required = ["{0}=<{0}>".format(arg) for arg in self.required_args]
        args_str = ' '.join(required + optionals)
        return "%s %s" % (self._func.__name__, args_str)


def poll_until(retriever, condition=lambda value: value,
               sleep_time=1, time_out=None):
    """Retrieves object until it passes condition, then returns it.

    If time_out_limit is passed in, PollTimeOut will be raised once that
    amount of time is eclipsed.

    """
    start_time = time.time()

    def poll_and_check():
        obj = retriever()
        if condition(obj):
            raise loopingcall.LoopingCallDone(retvalue=obj)
        if time_out is not None and time.time() - start_time > time_out:
            raise exception.PollTimeOut
    lc = loopingcall.LoopingCall(f=poll_and_check).start(sleep_time, True)
    return lc.wait()


# Copied from nova.api.openstack.common in the old code.
def get_id_from_href(href):
    """Return the id or uuid portion of a url.

    Given: 'http://www.foo.com/bar/123?q=4'
    Returns: '123'

    Given: 'http://www.foo.com/bar/abc123?q=4'
    Returns: 'abc123'

    """
    return urlparse.urlsplit("%s" % href).path.split('/')[-1]


def execute_with_timeout(*args, **kwargs):
    time = kwargs.pop('timeout', 30)
    log_output_on_error = kwargs.pop('log_output_on_error', False)

    timeout = Timeout(time)
    try:
        return execute(*args, **kwargs)
    except exception.ProcessExecutionError as e:
        if log_output_on_error:
            LOG.error(
                _("Command '%(cmd)s' failed. %(description)s "
                  "Exit code: %(exit_code)s\nstderr: %(stderr)s\n"
                  "stdout: %(stdout)s") %
                {'cmd': e.cmd, 'description': e.description or '',
                 'exit_code': e.exit_code, 'stderr': e.stderr,
                 'stdout': e.stdout})
        raise
    except Timeout as t:
        if t is not timeout:
            LOG.error(_("Got a timeout but not the one expected."))
            raise
        else:
            msg = (_("Time out after waiting "
                     "%(time)s seconds when running proc: %(args)s"
                     " %(kwargs)s.") % {'time': time, 'args': args,
                                        'kwargs': kwargs})
            LOG.error(msg)
            raise exception.ProcessExecutionError(msg)
    finally:
        timeout.cancel()


def correct_id_with_req(id, request):
    # Due to a shortcoming with the way Trove uses routes.mapper,
    # URL entities right of the last slash that contain at least
    # one . are routed to our service without that suffix, as
    # it was interpreted as a filetype This method looks at the
    # request, and if applicable, reattaches the suffix to the id.
    routing_args = request.environ.get('wsgiorg.routing_args', [])
    for routing_arg in routing_args:
        try:
            found = routing_arg.get('format', '')
            if found and found not in CONF.expected_filetype_suffixes:
                return "%s.%s" % (id, found)
        except (AttributeError, KeyError):
            # Not the relevant routing_args entry.
            pass
    return id


def generate_random_password(password_length=CONF.default_password_length):
    return passlib_utils.generate_password(size=password_length)


def try_recover(func):
    def _decorator(*args, **kwargs):
        recover_func = kwargs.pop("recover_func", None)
        try:
            func(*args, **kwargs)
        except Exception:
            if recover_func is not None:
                recover_func(func)
            else:
                LOG.debug("No recovery method defined for %(func)s" % {
                          'func': func.__name__})
            raise
    return _decorator


def gen_ports(portstr):
    from_port, sep, to_port = portstr.partition('-')
    if not (to_port and from_port):
        if not sep:
            to_port = from_port
    if int(from_port) > int(to_port):
        raise ValueError
    return from_port, to_port
