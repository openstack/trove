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

import abc
import six

from trove.common.strategies.strategy import Strategy
from trove.tests.config import CONFIG


@six.add_metaclass(abc.ABCMeta)
class TestGroup(object):

    TEST_RUNNERS_NS = 'trove.tests.scenario.runners'
    TEST_HELPERS_NS = 'trove.tests.scenario.helpers'
    TEST_HELPER_MODULE_NAME = 'test_helper'
    TEST_HELPER_BASE_NAME = 'TestHelper'

    def __init__(self, runner_module_name, runner_base_name, *args, **kwargs):
        self._test_runner = self.get_runner(
            runner_module_name, runner_base_name, *args, **kwargs)

    def get_runner(self, runner_module_name, runner_base_name,
                   *args, **kwargs):
        class_prefix = self._get_test_datastore()
        runner_cls = self._load_dynamic_class(
            runner_module_name, class_prefix, runner_base_name,
            self.TEST_RUNNERS_NS)
        runner = runner_cls(*args, **kwargs)
        runner._test_helper = self.get_helper()
        return runner

    def get_helper(self):
        class_prefix = self._get_test_datastore()
        helper_cls = self._load_dynamic_class(
            self.TEST_HELPER_MODULE_NAME, class_prefix,
            self.TEST_HELPER_BASE_NAME, self.TEST_HELPERS_NS)
        return helper_cls(self._build_class_name(
            class_prefix, self.TEST_HELPER_BASE_NAME, strip_test=True))

    def _get_test_datastore(self):
        return CONFIG.dbaas_datastore

    def _load_dynamic_class(self, module_name, class_prefix, base_name,
                            namespace):
        """Try to load a datastore specific class if it exists; use the
        default otherwise.
        """
        # This is for overridden Runner classes
        impl = self._build_class_path(module_name,
                                      class_prefix, base_name)
        cls = self._load_class('runner', impl, namespace)

        if not cls:
            # This is for overridden Helper classes
            module = module_name.replace('test', class_prefix.lower())
            impl = self._build_class_path(module, class_prefix, base_name,
                                          strip_test=True)
            cls = self._load_class('helper', impl, namespace)

        if not cls:
            # Just import the base class
            impl = self._build_class_path(module_name, '', base_name)
            cls = self._load_class(None, impl, namespace)

        return cls

    def _load_class(self, load_type, impl, namespace):
        cls = None
        if not load_type or load_type in impl.lower():
            try:
                cls = Strategy.get_strategy(impl, namespace)
            except ImportError as ie:
                # Only fail silently if it's something we expect,
                # such as a missing override class.  Anything else
                # shouldn't be suppressed.
                l_msg = ie.message.lower()
                if load_type not in l_msg or (
                        'no module named' not in l_msg and
                        'cannot be found' not in l_msg):
                    raise
        return cls

    def _build_class_path(self, module_name, class_prefix, class_base,
                          strip_test=False):
        class_name = self._build_class_name(class_prefix, class_base,
                                            strip_test)
        return '%s.%s' % (module_name, class_name)

    def _build_class_name(self, class_prefix, base_name, strip_test=False):
        base = (base_name.replace('Test', '') if strip_test else base_name)
        return '%s%s' % (class_prefix.capitalize(), base)

    @property
    def test_runner(self):
        return self._test_runner
