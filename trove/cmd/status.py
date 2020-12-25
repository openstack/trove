# Copyright (c) 2018 NEC, Corp.
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

import sys

from oslo_config import cfg
from oslo_upgradecheck import common_checks
from oslo_upgradecheck import upgradecheck

from trove.common.i18n import _
from trove import db
from trove.instance.models import DBInstance
from trove.instance.tasks import InstanceTasks


class Checks(upgradecheck.UpgradeCommands):
    """Various upgrade checks should be added as separate methods in this class
    and added to _upgrade_checks tuple.
    """

    def _check_instances_with_running_tasks(self):
        """Finds Trove instances with running tasks.

        Such instances need to communicate with Trove control plane to report
        status. This may rise issues if Trove services are unavailable, e.g.
        Trove guest agent may be left in a failed state due to communication
        issues.
        """

        db_api = db.get_db_api()
        db_api.configure_db(cfg.CONF)

        query = DBInstance.query()
        query = query.filter(DBInstance.task_status != InstanceTasks.NONE)
        query = query.filter_by(deleted=False)
        instances_with_tasks = query.count()

        if instances_with_tasks:
            return upgradecheck.Result(
                upgradecheck.Code.WARNING,
                _("Instances with running tasks exist."))

        return upgradecheck.Result(upgradecheck.Code.SUCCESS)

    # The format of the check functions is to return an
    # oslo_upgradecheck.upgradecheck.Result
    # object with the appropriate
    # oslo_upgradecheck.upgradecheck.Code and details set.
    # If the check hits warnings or failures then those should be stored
    # in the returned Result's "details" attribute. The
    # summary will be rolled up at the end of the check() method.
    _upgrade_checks = (
        (_("instances_with_running_tasks"),
         _check_instances_with_running_tasks),
        (_('policy File JSON to YAML Migration'),
         (common_checks.check_policy_json, {'conf': cfg.CONF})),
    )


def main():
    return upgradecheck.main(
        cfg.CONF, project="trove", upgrade_command=Checks())


if __name__ == '__main__':
    sys.exit(main())
