# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack Foundation
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

import datetime
from reddwarf.openstack.common import timeutils


class LimitView(object):

    def __init__(self, rate_limit):
        self.rate_limit = rate_limit

    def data(self):
        get_utc = datetime.datetime.utcfromtimestamp
        next_avail = get_utc(self.rate_limit.get("resetTime", 0))

        return {"limit": {
            "nextAvailable": timeutils.isotime(at=next_avail),
            "remaining": self.rate_limit.get("remaining", 0),
            "unit": self.rate_limit.get("unit", ""),
            "value": self.rate_limit.get("value", ""),
            "verb": self.rate_limit.get("verb", ""),
            "uri": self.rate_limit.get("URI", ""),
            "regex": self.rate_limit.get("regex", "")
        }
        }


class LimitViews(object):

    def __init__(self, abs_limits, rate_limits):
        self.abs_limits = abs_limits
        self.rate_limits = rate_limits

    def data(self):
        data = []
        abs_view = dict()
        abs_view["verb"] = "ABSOLUTE"
        for resource_name, abs_limit in self.abs_limits.items():
            abs_view["max_" + resource_name] = abs_limit

        data.append(abs_view)
        for l in self.rate_limits:
            data.append(LimitView(l).data()["limit"])
        return {"limits": data}
