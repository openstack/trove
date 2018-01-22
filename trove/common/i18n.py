#    Copyright 2014 Tesora, Inc.
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

"""oslo.i18n integration module.

See https://docs.openstack.org/oslo.i18n/latest/user/index.html

"""

import oslo_i18n


# NOTE(dhellmann): This reference to o-s-l-o will be replaced by the
# application name when this module is synced into the separate
# repository. It is OK to have more than one translation function
# using the same domain, since there will still only be one message
# catalog.
_translators = oslo_i18n.TranslatorFactory(domain='trove')

# The primary translation function using the well-known name "_"
_ = _translators.primary
