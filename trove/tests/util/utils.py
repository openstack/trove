# Copyright 2016 Tesora Inc.
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


import time

from functools import wraps
from oslo_log import log as logging

from trove.common.i18n import _


LOG = logging.getLogger(__name__)


def retry(expected_exception_cls, retries=3, delay_fun=lambda n: 3 * n):
    """Retry decorator.
    Executes the decorated function N times with a variable timeout
    on a given exception(s).

    :param expected_exception_cls: Handled exception classes.
    :type expected_exception_cls:  class or tuple of classes

    :param delay_fun:              The time delay in sec as a function of the
                                   number of attempts (n) already executed.
    :type delay_fun:               callable
    """
    def retry_deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            remaining_attempts = retries
            while remaining_attempts > 1:
                try:
                    return f(*args, **kwargs)
                except expected_exception_cls:
                    remaining_attempts -= 1
                    delay = delay_fun(retries - remaining_attempts)
                    LOG.exception(_(
                        "Retrying in %(delay)d seconds "
                        "(remaining attempts: %(remaining)d)...") %
                        {'delay': delay, 'remaining': remaining_attempts})
                    time.sleep(delay)
            return f(*args, **kwargs)
        return wrapper
    return retry_deco
