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


def update_dict(updates, target):
    """Recursively update a target dictionary with given updates.

    Updates are provided as a dictionary of key-value pairs
    where a value can also be a nested dictionary in which case
    its key is treated as a sub-section of the outer key.
    If a list value is encountered the update is applied
    iteratively on all its items.
    """
    if isinstance(target, list):
        for index, item in enumerate(target):
            target[index] = update_dict(updates, item)
        return target

    for k, v in updates.iteritems():
        if isinstance(v, collections.Mapping):
            target[k] = update_dict(v, target.get(k, {}))
        else:
            target[k] = updates[k]

    return target


def build_file_path(base_dir, base_name, *extensions):
    """Build a path to a file in a given directory.
    The file may have an extension(s).

    :returns:    Path such as: 'base_dir/base_name.ext1.ext2.ext3'
    """
    file_name = os.extsep.join([base_name] + list(extensions))
    return os.path.join(base_dir, file_name)
