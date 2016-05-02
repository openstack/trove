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

import collections
import os
import re

import six


def update_dict(updates, target):
    """Recursively update a target dictionary with given updates.

    Updates are provided as a dictionary of key-value pairs
    where a value can also be a nested dictionary in which case
    its key is treated as a sub-section of the outer key.
    If a list value is encountered the update is applied
    iteratively on all its items.

    :returns:    Will always return a dictionary of results (may be empty).
    """
    if target is None:
        target = {}

    if isinstance(target, list):
        for index, item in enumerate(target):
            target[index] = update_dict(updates, item)
        return target

    if updates is not None:
        for k, v in updates.items():
            if isinstance(v, collections.Mapping):
                target[k] = update_dict(v, target.get(k, {}))
            else:
                target[k] = updates[k]

    return target


def expand_dict(target, namespace_sep='.'):
    """Expand a flat dict to a nested one.
    This is an inverse of 'flatten_dict'.

    :seealso: flatten_dict
    """
    nested = {}
    for k, v in target.items():
        sub = nested
        keys = k.split(namespace_sep)
        for key in keys[:-1]:
            sub = sub.setdefault(key, {})
        sub[keys[-1]] = v

    return nested


def flatten_dict(target, namespace_sep='.'):
    """Flatten a nested dict.
    Return a one-level dict with all sub-level keys joined by a namespace
    separator.

    The following nested dict:
    {'ns1': {'ns2a': {'ns3a': True, 'ns3b': False}, 'ns2b': 10}}

    would be flattened to:
    {'ns1.ns2a.ns3a': True, 'ns1.ns2a.ns3b': False, 'ns1.ns2b': 10}
    """
    def flatten(target, keys, namespace_sep):
        flattened = {}
        if isinstance(target, collections.Mapping):
            for k, v in target.items():
                flattened.update(
                    flatten(v, keys + [k], namespace_sep))
        else:
            ns = namespace_sep.join(keys)
            flattened[ns] = target

        return flattened

    return flatten(target, [], namespace_sep)


def build_file_path(base_dir, base_name, *extensions):
    """Build a path to a file in a given directory.
    The file may have an extension(s).

    :returns:    Path such as: 'base_dir/base_name.ext1.ext2.ext3'
    """
    file_name = os.extsep.join([base_name] + list(extensions))
    return os.path.expanduser(os.path.join(base_dir, file_name))


def to_bytes(value):
    """Convert numbers with a byte suffix to bytes.
    """
    if isinstance(value, six.string_types):
        pattern = re.compile('^(\d+)([K,M,G]{1})$')
        match = pattern.match(value)
        if match:
            value = match.group(1)
            suffix = match.group(2)
            factor = {
                'K': 1024,
                'M': 1024 ** 2,
                'G': 1024 ** 3,
            }[suffix]

            return str(int(round(factor * float(value))))

    return value
