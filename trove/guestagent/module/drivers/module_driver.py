# Copyright 2016 Tesora, Inc.
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

import abc
import functools
import re
import six

from oslo_log import log as logging

from trove.common import exception


LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class ModuleDriver(object):
    """Base class that defines the contract for module drivers.

    Note that you don't have to derive from this class to have a valid
    driver; it is purely a convenience. Any class that adheres to the
    'interface' as dictated by this class' abstractmethod decorators
    (and other methods such as get_type, get_name and configure)
    will work.
    """
    def __init__(self):
        super(ModuleDriver, self).__init__()

        # This is used to store any message args to be substituted by
        # the output decorator when logging/returning messages.
        self._module_message_args = {}
        self._message_args = None
        self._generated_name = None

    @property
    def message_args(self):
        """Return a dict of message args that can be used to enhance
        the output decorator messages. This shouldn't be overridden; use
        self.message_args = <dict> instead to append values.
        """
        if not self._message_args:
            self._message_args = {
                'name': self.get_name(),
                'type': self.get_type()}
            self._message_args.update(self._module_message_args)
        return self._message_args

    @message_args.setter
    def message_args(self, values):
        """Set the message args that can be used to enhance
        the output decorator messages.
        """
        values = values or {}
        self._module_message_args = values
        self._message_args = None

    @property
    def generated_name(self):
        if not self._generated_name:
            # Turn class name into 'module type' format.
            # For example: DoCustomWorkDriver -> do_custom_work
            temp = re.sub('(.)[Dd]river$', r'\1', self.__class__.__name__)
            temp2 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', temp)
            temp3 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', temp2)
            self._generated_name = temp3.lower()
        return self._generated_name

    def get_type(self):
        """This is used when setting up a module in Trove, and is here for
        code clarity.  It just returns the name of the driver by default.
        """
        return self.get_name()

    def get_name(self):
        """Use the generated name based on the class name. If
        overridden, must be in lower-case.
        """
        return self.generated_name

    @abc.abstractmethod
    def get_description(self):
        """Description for the driver."""
        pass

    @abc.abstractmethod
    def get_updated(self):
        """Date the driver was last updated."""
        pass

    @abc.abstractmethod
    def apply(self, name, datastore, ds_version, data_file, admin_module):
        """Apply the module to the guest instance. Return status and message
        as a tuple. Passes in whether the module was created with 'admin'
        privileges. This can be used as a form of access control by having
        the driver refuse to apply a module if it wasn't created with options
        that indicate that it was done by an 'admin' user.
        """
        return False, "Not a concrete driver"

    @abc.abstractmethod
    def remove(self, name, datastore, ds_version, data_file):
        """Remove the module from the guest instance.  Return
        status and message as a tuple.
        """
        return False, "Not a concrete driver"

    def configure(self, name, datastore, ds_version, data_file):
        """Configure the driver.  This is particularly useful for adding values
        to message_args, by having a line such as: self.message_args = <dict>.
        These values will be appended to the default ones defined
        in the message_args @property.
        """
        pass


def output(log_message=None, success_message=None,
           fail_message=None):
    """This is a decorator to trap the typical exceptions that occur
    when applying and removing modules. It returns the proper output
    corresponding to the error messages automatically. If the function
    returns output (success_flag, message) then those are returned,
    otherwise success is assumed and the success_message returned.
    Using this removes a lot of potential boiler-plate code, however
    it is not necessary.
    Keyword arguments can be used in the message string. Default
    values can be found in the message_args @property, however a
    driver can add whatever it see fit, by setting message_args
    to a dict in the configure call (see above). Thus if you set
    self.message_args = {'my_key': 'my_key_val'} then the message
    string could look like "My key is '$(my_key)s'".
    """
    success_message = success_message or "Success"
    fail_message = fail_message or "Fail"

    def output_decorator(func):
        """This is the actual decorator."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """Here's where we handle the error messages and return values
            from the actual function.
            """
            log_msg = log_message
            success_msg = success_message
            fail_msg = fail_message
            if isinstance(args[0], ModuleDriver):
                # Try and insert any message args if they exist in the driver
                message_args = args[0].message_args
                if message_args:
                    try:
                        log_msg = log_msg % message_args
                        success_msg = success_msg % message_args
                        fail_msg = fail_msg % message_args
                    except Exception:
                        # if there's a problem, just log it and drive on
                        LOG.warning("Could not apply message args: %s",
                                    message_args)
                        pass

            if log_msg:
                LOG.info(log_msg)
            success = False
            try:
                rv = func(*args, **kwargs)
                if rv:
                    # Use the actual values, if there are some
                    success, message = rv
                else:
                    success = True
                    message = success_msg
            except exception.ProcessExecutionError as ex:
                message = ("%(msg)s: %(out)s\n%(err)s" %
                           {'msg': fail_msg,
                            'out': ex.stdout,
                            'err': ex.stderr})
                message = message.replace(': \n', ': ')
                message = message.rstrip()
                LOG.exception(message)
            except exception.TroveError as ex:
                message = ("%(msg)s: %(err)s" %
                           {'msg': fail_msg, 'err': ex._error_string})
                LOG.exception(message)
            except Exception as ex:
                message = ("%(msg)s: %(err)s" %
                           {'msg': fail_msg, 'err': str(ex)})
                LOG.exception(message)
            return success, message

        return wrapper

    return output_decorator
