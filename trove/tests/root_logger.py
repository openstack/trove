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

import logging
import traceback


class DefaultRootHandler(logging.StreamHandler):
    """A singleton StreamHandler"""
    __handler = logging.StreamHandler()
    __singleton = None
    __info = None

    @classmethod
    def activate(cls):
        # leverage the singleton __handler which has an
        # acquire() method to create a critical section.
        cls.__handler.acquire()
        if cls.__singleton is None:
            cls.__singleton = DefaultRootHandler()

        cls.__handler.release()
        return cls.__singleton

    @classmethod
    def set_info(cls, info=None):
        cls.__info = info

    def __init__(self):
        if DefaultRootHandler.__singleton is not None:
            raise Exception(
                "Do not directly instantiate DefaultRootHandler(). "
                "Only use the activate() class method.")

        super(DefaultRootHandler, self).__init__()

    def emit(self, record):
        msg = ("[" + record.name + "]\n" +
               self.format(record) + "\n" +
               (("\tFrom: " + DefaultRootHandler.__info + "\n")
                if DefaultRootHandler.__info
                else (''.join(traceback.format_stack()))))
        self.stream.write(msg)
        self.flush()


class DefaultRootLogger(object):
    """A root logger that uses the singleton handler"""

    def __init__(self):
        super(DefaultRootLogger, self).__init__()
        handler = DefaultRootHandler.activate()

        handler.acquire()
        if handler not in logging.getLogger('').handlers:
            logging.getLogger('').addHandler(handler)

        handler.release()
