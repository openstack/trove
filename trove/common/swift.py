# Copyright 2021 Catalyst Cloud Ltd.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.


def parse_location(location):
    storage_url = "/".join(location.split('/')[:-2])
    container_name = location.split('/')[-2]
    object_name = location.split('/')[-1]
    return storage_url, container_name, object_name


def _get_attr(original):
    """Get a friendly name from an object header key."""
    key = original.replace('-', '_')
    key = key.replace('x_object_meta_', '')
    return key


def get_metadata(client, location, extra_attrs=[]):
    _, container_name, object_name = parse_location(location)
    headers = client.head_object(container_name, object_name)

    meta = {}
    for key, value in headers.items():
        if key.startswith('x-object-meta'):
            meta[_get_attr(key)] = value

    for key in extra_attrs:
        meta[key] = headers.get(key)

    return meta
