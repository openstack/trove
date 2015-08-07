# Copyright 2015 Tesora Inc.
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

from enum import Enum
import inspect
from proboscis import SkipTest


class DataType(Enum):
    """
    Represent the type of data to add to a datastore.  This allows for
    multiple 'states' of data that can be verified after actions are
    performed by Trove.
    """

    # very tiny amount of data, useful for testing replication
    # propagation, etc.
    tiny = 1
    # small amount of data (this can be added to each instance
    # after creation, for example).
    small = 2
    # large data, enough to make creating a backup take 20s or more.
    large = 3


class TestHelper(object):
    """
    Base class for all 'Helper' classes.

    The Helper classes are designed to do datastore specific work
    that can be used by multiple runner classes.  Things like adding
    data to datastores and verifying data or internal database states,
    etc. should be handled by these classes.
    """

    # Define the actions that can be done on each DataType
    FN_ACTION_ADD = 'add'
    FN_ACTION_REMOVE = 'remove'
    FN_ACTION_VERIFY = 'verify'
    FN_ACTIONS = [FN_ACTION_ADD, FN_ACTION_REMOVE, FN_ACTION_VERIFY]

    def __init__(self, expected_override_name):
        """Initialize the helper class by creating a number of stub
        functions that each datastore specific class can chose to
        override.  Basically, the functions are of the form:
            {FN_ACTION_*}_{DataType.name}_data
        For example:
            add_tiny_data
            add_small_data
            remove_small_data
            verify_large_data
        and so on.  Add and remove actions throw a SkipTest if not
        implemented, and verify actions by default do nothing.
        """
        super(TestHelper, self).__init__()

        self._ds_client = None
        self._current_host = None

        self._expected_override_name = expected_override_name

        # For building data access functions
        # name/fn pairs for each action
        self._data_fns = {self.FN_ACTION_ADD: {},
                          self.FN_ACTION_REMOVE: {},
                          self.FN_ACTION_VERIFY: {}}
        # Types of data functions to create.
        # Pattern used to create the data functions.  The first parameter
        # is the function type (FN_ACTION_*), the second is the DataType
        self.data_fn_pattern = '%s_%s_data'
        self._build_data_fns()

    def get_client(self, host, *args, **kwargs):
        """Gets the datastore client."""
        if not self._ds_client or self._current_host != host:
            self._ds_client = self.create_client(host, *args, **kwargs)
            self._current_host = host
        return self._ds_client

    def create_client(self, host, *args, **kwargs):
        """Create a datastore client."""
        raise SkipTest('No client defined')

    def add_data(self, data_type, host, *args, **kwargs):
        """Adds data of type 'data_type' to the database.  Descendant
        classes should implement a function for each DataType value
        of the form 'add_{DataType.name}_data' - for example:
            'add_tiny_data'
            'add_small_data'
            ...
        Since this method may be called multiple times, the implemented
        'add_*_data' functions should be idempotent.
        """
        self._perform_data_action(self.FN_ACTION_ADD, data_type, host,
                                  *args, **kwargs)

    def remove_data(self, data_type, host, *args, **kwargs):
        """Removes all data associated with 'data_type'.  See
        instructions for 'add_data' for implementation guidance.
        """
        self._perform_data_action(self.FN_ACTION_REMOVE, data_type, host,
                                  *args, **kwargs)

    def verify_data(self, data_type, host, *args, **kwargs):
        """Verify that the data of type 'data_type' exists in the
        datastore.  This can be done by testing edge cases, and possibly
        some random elements within the set.  See
        instructions for 'add_data' for implementation guidance.
        """
        self._perform_data_action(self.FN_ACTION_VERIFY, data_type, host,
                                  *args, **kwargs)

    def _perform_data_action(self, action_type, data_type, host,
                             *args, **kwargs):
        fns = self._data_fns[action_type]
        data_fn_name = self.data_fn_pattern % (action_type, data_type.name)
        try:
            fns[data_fn_name](self, host, *args, **kwargs)
        except SkipTest:
            raise
        except Exception as ex:
            raise RuntimeError("Error calling %s from class %s - %s" %
                               (data_fn_name, self.__class__.__name__, ex))

    def _build_data_fns(self):
        """Build the base data functions specified by FN_ACTION_*
        for each of the types defined in the DataType class.  For example,
        'add_small_data' and 'verify_large_data'.  These
        functions can be overwritten by a descendant class and
        those overwritten functions will be bound before calling
        any data functions such as 'add_data' or 'remove_data'.
        """
        for fn_type in self.FN_ACTIONS:
            fn_dict = self._data_fns[fn_type]
            for data_type in DataType:
                self._data_fn_builder(fn_type, data_type, fn_dict)
        self._override_data_fns()

    def _data_fn_builder(self, fn_type, data_type, fn_dict):
        """Builds the actual function with a SkipTest exception,
        and changes the name to reflect the pattern.
        """
        name = self.data_fn_pattern % (fn_type, data_type.name)

        def data_fn(self, host, *args, **kwargs):
            # default action is to skip the test
            using_str = ''
            if self._expected_override_name != self.__class__.__name__:
                using_str = ' (using %s)' % self.__class__.__name__
            raise SkipTest("Data function '%s' not found in '%s'%s" %
                           (name, self._expected_override_name, using_str))

        data_fn.__name__ = data_fn.func_name = name
        fn_dict[name] = data_fn

    def _override_data_fns(self):
        """Bind the override methods to the dict."""
        members = inspect.getmembers(self.__class__,
                                     predicate=inspect.ismethod)
        for fn_action in self.FN_ACTIONS:
            fns = self._data_fns[fn_action]
            for name, fn in members:
                if name in fns:
                    fns[name] = fn
