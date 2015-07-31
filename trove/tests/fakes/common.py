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

"""Common code to help in faking the models."""

from novaclient import exceptions as nova_exceptions
from oslo_log import log as logging

from trove.common import cfg


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def authorize(context):
    if not context.is_admin:
        raise nova_exceptions.Forbidden(403, "Forbidden")
