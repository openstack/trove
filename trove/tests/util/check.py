# Copyright (c) 2012 OpenStack
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

"""Like asserts, but does not raise an exception until the end of a block."""

import traceback
from proboscis.asserts import ASSERTION_ERROR
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis.asserts import Check


def get_stack_trace_of_caller(level_up):
    """Gets the stack trace at the point of the caller."""
    level_up += 1
    st = traceback.extract_stack()
    caller_index = len(st) - level_up
    if caller_index < 0:
        caller_index = 0
    new_st = st[0:caller_index]
    return new_st


def raise_blame_caller(level_up, ex):
    """Raises an exception, changing the stack trace to point to the caller."""
    new_st = get_stack_trace_of_caller(level_up + 2)
    raise type(ex), ex, new_st


class Checker(object):

    def __init__(self):
        self.messages = []
        self.odd = True
        self.protected = False

    def _add_exception(self, _type, value, tb):
        """Takes an exception, and adds it as a string."""
        if self.odd:
            prefix = "* "
        else:
            prefix = "- "
        start = "Check failure! Traceback:"
        middle = prefix.join(traceback.format_list(tb))
        end = '\n'.join(traceback.format_exception_only(_type, value))
        msg = '\n'.join([start, middle, end])
        self.messages.append(msg)
        self.odd = not self.odd

    def equal(self, *args, **kwargs):
        self._run_assertion(assert_equal, *args, **kwargs)

    def false(self, *args, **kwargs):
        self._run_assertion(assert_false, *args, **kwargs)

    def not_equal(self, *args, **kwargs):
        _run_assertion(assert_not_equal, *args, **kwargs)

    def _run_assertion(self, assert_func, *args, **kwargs):
        """
        Runs an assertion method, but catches any failure and adds it as a
        string to the messages list.
        """
        if self.protected:
            try:
                assert_func(*args, **kwargs)
            except ASSERTION_ERROR as ae:
                st = get_stack_trace_of_caller(2)
                self._add_exception(ASSERTION_ERROR, ae, st)
        else:
            assert_func(*args, **kwargs)

    def __enter__(self):
        self.protected = True
        return self

    def __exit__(self, _type, value, tb):
        self.protected = False
        if _type is not None:
            # An error occurred other than an assertion failure.
            # Return False to allow the Exception to be raised
            return False
        if len(self.messages) != 0:
            final_message = '\n'.join(self.messages)
            raise ASSERTION_ERROR(final_message)

    def true(self, *args, **kwargs):
        self._run_assertion(assert_true, *args, **kwargs)


class AttrCheck(Check):
    """Class for attr checks, links and other common items."""

    def __init__(self):
        super(AttrCheck, self).__init__()

    def fail(self, msg):
        self.true(False, msg)

    def attrs_exist(self, list, expected_attrs, msg=None):
        # Check these attrs only are returned in create response
        for attr in list:
            if attr not in expected_attrs:
                self.fail("%s should not contain '%s'" % (msg, attr))

    def links(self, links):
        expected_attrs = ['href', 'rel']
        for link in links:
            self.attrs_exist(link, expected_attrs, msg="Links")


class CollectionCheck(Check):
    """Checks for elements in a dictionary."""

    def __init__(self, name, collection):
        self.name = name
        self.collection = collection
        super(CollectionCheck, self).__init__()

    def element_equals(self, key, expected_value):
        if key not in self.collection:
            message = 'Element "%s.%s" does not exist.' % (self.name, key)
            self.fail(message)
        else:
            value = self.collection[key]
            self.equal(value, expected_value)

    def has_element(self, key, element_type):
        if key not in self.collection:
            message = 'Element "%s.%s" does not exist.' % (self.name, key)
            self.fail(message)
        else:
            value = self.collection[key]
            match = False
            if not isinstance(element_type, tuple):
                type_list = [element_type]
            else:
                type_list = element_type
            for possible_type in type_list:
                if possible_type is None:
                    if value is None:
                        match = True
                else:
                    if isinstance(value, possible_type):
                        match = True
            if not match:
                self.fail('Element "%s.%s" does not match any of these '
                          'expected types: %s' % (self.name, key, type_list))


class TypeCheck(Check):
    """Checks for attributes in an object."""

    def __init__(self, name, instance):
        self.name = name
        self.instance = instance
        super(TypeCheck, self).__init__()

    def _check_type(value, attribute_type):
        if not isinstance(value, attribute_type):
            self.fail("%s attribute %s is of type %s (expected %s)."
                      % (self.name, attribute_name, type(value),
                         attribute_type))

    def has_field(self, attribute_name, attribute_type,
                  additional_checks=None):
        if not hasattr(self.instance, attribute_name):
            self.fail("%s missing attribute %s." % (self.name, attribute_name))
        else:
            value = getattr(self.instance, attribute_name)
            match = False
            if isinstance(attribute_type, tuple):
                type_list = attribute_type
            else:
                type_list = [attribute_type]
            for possible_type in type_list:
                if possible_type is None:
                    if value is None:
                        match = True
                else:
                    if isinstance(value, possible_type):
                        match = True
            if not match:
                self.fail("%s attribute %s is of type %s (expected one of "
                          "the following: %s)." % (self.name, attribute_name,
                          type(value), attribute_type))
            if match and additional_checks:
                additional_checks(value)
