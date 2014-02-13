# Copyright 2010-2011 OpenStack Foundation
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


from trove.common import wsgi


def create_links(resource_path, request, id):
    """Creates the links dictionary in the format typical of most resources."""
    context = request.environ[wsgi.CONTEXT_KEY]
    link_info = {
        'host': request.host,
        'version': request.url_version,
        'tenant_id': context.tenant,
        'resource_path': resource_path,
        'id': id,
    }
    return [
        {
            "href": "https://%(host)s/v%(version)s/%(tenant_id)s"
                    "/%(resource_path)s/%(id)s" % link_info,
            "rel": "self"
        },
        {
            "href": "https://%(host)s/%(resource_path)s/%(id)s" % link_info,
            "rel": "bookmark"
        }
    ]
