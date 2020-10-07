# Copyright 2020 Catalyst Cloud
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
from glanceclient import exc as glance_exceptions

from trove.common import exception


def get_image_id(client, image_id, image_tags):
    """Get and check image ID."""
    if image_id:
        try:
            client.images.get(image_id)
        except glance_exceptions.HTTPNotFound:
            raise exception.ImageNotFound(uuid=image_id)
        return image_id

    elif image_tags:
        filters = {'tag': image_tags, 'status': 'active'}
        images = list(client.images.list(
            filters=filters, sort='created_at:desc', limit=1))
        if not images:
            raise exception.ImageNotFoundByTags(tags=image_tags)
        image_id = images[0]['id']

    return image_id
