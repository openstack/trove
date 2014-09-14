# Copyright 2011 OpenStack Foundation.
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

"""
System-level utilities and helper functions.
"""

import re

import six


# NOTE(flaper87): The following globals are used by `mask_password`
_SANITIZE_KEYS = ['adminPass', 'admin_pass', 'password', 'admin_password']

# NOTE(ldbragst): Let's build a list of regex objects using the list of
# _SANITIZE_KEYS we already have. This way, we only have to add the new key
# to the list of _SANITIZE_KEYS and we can generate regular expressions
# for XML and JSON automatically.
_SANITIZE_PATTERNS_2 = []
_SANITIZE_PATTERNS_1 = []

# NOTE(amrith): Some regular expressions have only one parameter, some
# have two parameters. Use different lists of patterns here.
_FORMAT_PATTERNS_1 = [r'(%(key)s\s*[=]\s*)[^\s^\'^\"]+']
_FORMAT_PATTERNS_2 = [r'(%(key)s\s*[=]\s*[\"\']).*?([\"\'])',
                      r'(%(key)s\s+[\"\']).*?([\"\'])',
                      r'([-]{2}%(key)s\s+)[^\'^\"^=^\s]+([\s]*)',
                      r'(<%(key)s>).*?(</%(key)s>)',
                      r'([\"\']%(key)s[\"\']\s*:\s*[\"\']).*?([\"\'])',
                      r'([\'"].*?%(key)s[\'"]\s*:\s*u?[\'"]).*?([\'"])',
                      r'([\'"].*?%(key)s[\'"]\s*,\s*\'--?[A-z]+\'\s*,\s*u?'
                      '[\'"]).*?([\'"])',
                      r'(%(key)s\s*--?[A-z]+\s*)\S+(\s*)']

for key in _SANITIZE_KEYS:
    for pattern in _FORMAT_PATTERNS_2:
        reg_ex = re.compile(pattern % {'key': key}, re.DOTALL)
        _SANITIZE_PATTERNS_2.append(reg_ex)

    for pattern in _FORMAT_PATTERNS_1:
        reg_ex = re.compile(pattern % {'key': key}, re.DOTALL)
        _SANITIZE_PATTERNS_1.append(reg_ex)


def mask_password(message, secret="***"):
    """Replace password with 'secret' in message.

    :param message: The string which includes security information.
    :param secret: value with which to replace passwords.
    :returns: The unicode value of message with the password fields masked.

    For example:

    >>> mask_password("'adminPass' : 'aaaaa'")
    "'adminPass' : '***'"
    >>> mask_password("'admin_pass' : 'aaaaa'")
    "'admin_pass' : '***'"
    >>> mask_password('"password" : "aaaaa"')
    '"password" : "***"'
    >>> mask_password("'original_password' : 'aaaaa'")
    "'original_password' : '***'"
    >>> mask_password("u'original_password' :   u'aaaaa'")
    "u'original_password' :   u'***'"
    """
    message = six.text_type(message)

    # NOTE(ldbragst): Check to see if anything in message contains any key
    # specified in _SANITIZE_KEYS, if not then just return the message since
    # we don't have to mask any passwords.
    if not any(key in message for key in _SANITIZE_KEYS):
        return message

    substitute = r'\g<1>' + secret + r'\g<2>'
    for pattern in _SANITIZE_PATTERNS_2:
        message = re.sub(pattern, substitute, message)

    substitute = r'\g<1>' + secret
    for pattern in _SANITIZE_PATTERNS_1:
        message = re.sub(pattern, substitute, message)

    return message
