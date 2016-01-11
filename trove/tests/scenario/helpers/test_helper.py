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
from time import sleep


class DataType(Enum):

    """
    Represent the type of data to add to a datastore.  This allows for
    multiple 'states' of data that can be verified after actions are
    performed by Trove.
    If new entries are added here, sane values should be added to the
    _fn_data dictionary defined in TestHelper.
    """

    # micro amount of data, useful for testing datastore logging, etc.
    micro = 1
    # another micro dataset (also for datastore logging)
    micro2 = 2
    # very tiny amount of data, useful for testing replication
    # propagation, etc.
    tiny = 3
    # another tiny dataset (also for replication propagation)
    tiny2 = 4
    # small amount of data (this can be added to each instance
    # after creation, for example).
    small = 5
    # large data, enough to make creating a backup take 20s or more.
    large = 6


class TestHelper(object):

    """
    Base class for all 'Helper' classes.

    The Helper classes are designed to do datastore specific work
    that can be used by multiple runner classes.  Things like adding
    data to datastores and verifying data or internal database states,
    etc. should be handled by these classes.
    """

    # Define the actions that can be done on each DataType.  When adding
    # a new action, remember to modify _data_fns
    FN_ADD = 'add'
    FN_REMOVE = 'remove'
    FN_VERIFY = 'verify'
    FN_TYPES = [FN_ADD, FN_REMOVE, FN_VERIFY]

    # Artificial 'DataType' name to use for the methods that do the
    # actual data manipulation work.
    DT_ACTUAL = 'actual'

    def __init__(self, expected_override_name):
        """Initialize the helper class by creating a number of stub
        functions that each datastore specific class can chose to
        override.  Basically, the functions are of the form:
            {FN_TYPE}_{DataType.name}_data
        For example:
            add_tiny_data
            add_small_data
            remove_small_data
            verify_large_data
        and so on.  Add and remove actions throw a SkipTest if not
        implemented, and verify actions by default do nothing.
        These methods, by default, call the corresponding *_actual_data()
        passing in 'data_label', 'data_start' and 'data_size' as defined
        for each DataType in the dictionary below.
        """
        super(TestHelper, self).__init__()

        self._expected_override_name = expected_override_name

        # For building data access functions
        # name/fn pairs for each action
        self._data_fns = {self.FN_ADD: {},
                          self.FN_REMOVE: {},
                          self.FN_VERIFY: {}}
        # Pattern used to create the data functions.  The first parameter
        # is the function type (FN_TYPE), the second is the DataType
        # or DT_ACTUAL.
        self.data_fn_pattern = '%s_%s_data'
        # Values to distinguish between the different DataTypes.  If these
        # values don't work for a datastore, it will need to override
        # the auto-generated {FN_TYPE}_{DataType.name}_data method.
        self.DATA_START = 'start'
        self.DATA_SIZE = 'size'
        self._fn_data = {
            DataType.micro.name: {
                self.DATA_START: 100,
                self.DATA_SIZE: 10},
            DataType.micro2.name: {
                self.DATA_START: 200,
                self.DATA_SIZE: 10},
            DataType.tiny.name: {
                self.DATA_START: 1000,
                self.DATA_SIZE: 100},
            DataType.tiny2.name: {
                self.DATA_START: 2000,
                self.DATA_SIZE: 100},
            DataType.small.name: {
                self.DATA_START: 10000,
                self.DATA_SIZE: 1000},
            DataType.large.name: {
                self.DATA_START: 100000,
                self.DATA_SIZE: 100000},
        }

        self._build_data_fns()

    #################
    # Utility methods
    #################
    def get_class_name(self):
        """Builds a string of the expected class name, plus the actual one
        being used if it's not the same.
        """
        class_name_str = "'%s'" % self._expected_override_name
        if self._expected_override_name != self.__class__.__name__:
            class_name_str += ' (using %s)' % self.__class__.__name__
        return class_name_str

    ################
    # Client related
    ################
    def get_client(self, host, *args, **kwargs):
        """Gets the datastore client. This isn't cached as the
        database may be restarted in between calls, causing
        lost connection errors.
        """
        return self.create_client(host, *args, **kwargs)

    def create_client(self, host, *args, **kwargs):
        """Create a datastore client.  This is datastore specific, so this
        method should be overridden if datastore access is desired.
        """
        raise SkipTest('No client defined')

    def get_helper_credentials(self):
        """Return the credentials that the client will be using to
        access the database.
        """
        return {'name': None, 'password': None, 'database': None}

    def get_helper_credentials_root(self):
        """Return the credentials that the client will be using to
        access the database as root.
        """
        return {'name': None, 'password': None}

    ##############
    # Data related
    ##############
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
        self._perform_data_action(self.FN_ADD, data_type.name, host,
                                  *args, **kwargs)

    def remove_data(self, data_type, host, *args, **kwargs):
        """Removes all data associated with 'data_type'.  See
        instructions for 'add_data' for implementation guidance.
        """
        self._perform_data_action(self.FN_REMOVE, data_type.name, host,
                                  *args, **kwargs)

    def verify_data(self, data_type, host, *args, **kwargs):
        """Verify that the data of type 'data_type' exists in the
        datastore.  This can be done by testing edge cases, and possibly
        some random elements within the set.  See
        instructions for 'add_data' for implementation guidance.
        """
        self._perform_data_action(self.FN_VERIFY, data_type.name, host,
                                  *args, **kwargs)

    def _perform_data_action(self, fn_type, fn_name, host, *args, **kwargs):
        fns = self._data_fns[fn_type]
        data_fn_name = self.data_fn_pattern % (fn_type, fn_name)
        try:
            fns[data_fn_name](self, host, *args, **kwargs)
        except SkipTest:
            raise
        except Exception as ex:
            raise RuntimeError("Error calling %s from class %s - %s" %
                               (data_fn_name, self.__class__.__name__, ex))

    def _build_data_fns(self):
        """Build the base data functions specified by FN_TYPE_*
        for each of the types defined in the DataType class.  For example,
        'add_small_data' and 'verify_large_data'.  These
        functions are set to call '*_actual_data' and will pass in
        sane values for label, start and size.  The '*_actual_data'
        methods should be overwritten by a descendant class, and are the
        ones that do the actual work.
        The original 'add_small_data', etc. methods can also be overridden
        if needed, and those overwritten functions will be bound before
        calling any data functions such as 'add_data' or 'remove_data'.
        """
        for fn_type in self.FN_TYPES:
            fn_dict = self._data_fns[fn_type]
            for data_type in DataType:
                self._data_fn_builder(fn_type, data_type.name, fn_dict)
            self._data_fn_builder(fn_type, self.DT_ACTUAL, fn_dict)
        self._override_data_fns()

    def _data_fn_builder(self, fn_type, fn_name, fn_dict):
        """Builds the actual function with a SkipTest exception,
        and changes the name to reflect the pattern.
        """
        data_fn_name = self.data_fn_pattern % (fn_type, fn_name)

        # Build the overridable 'actual' Data Manipulation methods
        if fn_name == self.DT_ACTUAL:
            def data_fn(self, data_label, data_start, data_size, host,
                        *args, **kwargs):
                # default action is to skip the test
                cls_str = ''
                if self._expected_override_name != self.__class__.__name__:
                    cls_str = (' (%s not loaded)' %
                               self._expected_override_name)
                raise SkipTest("Data function '%s' not found in '%s'%s" % (
                    data_fn_name, self.__class__.__name__, cls_str))
        else:
            def data_fn(self, host, *args, **kwargs):
                # call the corresponding 'actual' method
                fns = self._data_fns[fn_type]
                var_dict = self._fn_data[fn_name]
                data_start = var_dict[self.DATA_START]
                data_size = var_dict[self.DATA_SIZE]
                actual_fn_name = self.data_fn_pattern % (
                    fn_type, self.DT_ACTUAL)
                try:
                    fns[actual_fn_name](self, fn_name, data_start, data_size,
                                        host, *args, **kwargs)
                except SkipTest:
                    raise
                except Exception as ex:
                    raise RuntimeError("Error calling %s from class %s: %s" % (
                        data_fn_name, self.__class__.__name__, ex))

        data_fn.__name__ = data_fn.func_name = data_fn_name
        fn_dict[data_fn_name] = data_fn

    def _override_data_fns(self):
        """Bind the override methods to the dict."""
        members = inspect.getmembers(self.__class__,
                                     predicate=inspect.ismethod)
        for fn_type in self.FN_TYPES:
            fns = self._data_fns[fn_type]
            for name, fn in members:
                if name in fns:
                    fns[name] = fn

    #####################
    # Replication related
    #####################
    def wait_for_replicas(self):
        """Wait for data to propagate to all the replicas.  Datastore
        specific overrides could increase (or decrease) this delay.
        """
        sleep(30)

    #######################
    # Database/User related
    #######################
    def get_valid_database_definitions(self):
        """Return a list of valid database JSON definitions.
        These definitions will be used by tests that create databases.
        Return an empty list if the datastore does not support databases.
        """
        return list()

    def get_valid_user_definitions(self):
        """Return a list of valid user JSON definitions.
         These definitions will be used by tests that create users.
         Return an empty list if the datastore does not support users.
         """
        return list()

    def get_non_existing_database_definition(self):
        """Return a valid JSON definition for a non-existing database.
         This definition will be used by negative database tests.
         The database will not be created by any of the tests.
         Return None if the datastore does not support databases.
         """
        valid_defs = self.get_valid_database_definitions()
        return self._get_non_existing_definition(valid_defs)

    def get_non_existing_user_definition(self):
        """Return a valid JSON definition for a non-existing user.
         This definition will be used by negative user tests.
         The user will not be created by any of the tests.
         Return None if the datastore does not support users.
         """
        valid_defs = self.get_valid_user_definitions()
        return self._get_non_existing_definition(valid_defs)

    def _get_non_existing_definition(self, existing_defs):
        """This will create a unique definition for a non-existing object
        by randomizing one of an existing object.
        """
        if existing_defs:
            non_existing_def = dict(existing_defs[0])
            while non_existing_def in existing_defs:
                non_existing_def = self._randomize_on_name(non_existing_def)
            return non_existing_def

        return None

    def _randomize_on_name(self, definition):
        def_copy = dict(definition)
        def_copy['name'] = ''.join([def_copy['name'], 'rnd'])
        return def_copy

    #############################
    # Configuration Group related
    #############################
    def get_dynamic_group(self):
        """Return a definition of a dynamic configuration group.
        A dynamic group should contain only properties that do not require
        database restart.
        Return an empty dict if the datastore does not have any.
        """
        return dict()

    def get_non_dynamic_group(self):
        """Return a definition of a non-dynamic configuration group.
        A non-dynamic group has to include at least one property that requires
        database restart.
        Return an empty dict if the datastore does not have any.
        """
        return dict()

    def get_invalid_groups(self):
        """Return a list of configuration groups with invalid values.
        An empty list indicates that no 'invalid' tests should be run.
        """
        return []

    ###################
    # Guest Log related
    ###################
    def get_exposed_log_list(self):
        """Return the list of exposed logs for the datastore.  This
        method shouldn't need to be overridden.
        """
        logs = []
        try:
            logs.extend(self.get_exposed_user_log_names())
        except SkipTest:
            pass
        try:
            logs.extend(self.get_exposed_sys_log_names())
        except SkipTest:
            pass

        return logs

    def get_full_log_list(self):
        """Return the full list of all logs for the datastore.  This
        method shouldn't need to be overridden.
        """
        logs = self.get_exposed_log_list()
        try:
            logs.extend(self.get_unexposed_user_log_names())
        except SkipTest:
            pass
        try:
            logs.extend(self.get_unexposed_sys_log_names())
        except SkipTest:
            pass

        return logs

    # Override these guest log methods if needed
    def get_exposed_user_log_names(self):
        """Return the names of the user logs that are visible to all users.
        The first log name will be used for tests.
        """
        raise SkipTest("No exposed user log names defined.")

    def get_unexposed_user_log_names(self):
        """Return the names of the user logs that not visible to all users.
        The first log name will be used for tests.
        """
        raise SkipTest("No unexposed user log names defined.")

    def get_exposed_sys_log_names(self):
        """Return the names of SYS logs that are visible to all users.
        The first log name will be used for tests.
        """
        raise SkipTest("No exposed sys log names defined.")

    def get_unexposed_sys_log_names(self):
        """Return the names of the sys logs that not visible to all users.
        The first log name will be used for tests.
        """
        return ['guest']

    def log_enable_requires_restart(self):
        """Returns whether enabling or disabling a USER log requires a
        restart of the datastore.
        """
        return False

    ##############
    # Root related
    ##############
    def get_valid_root_password(self):
        """Return a valid password that can be used by a 'root' user.
        """
        return "RootTestPass"
