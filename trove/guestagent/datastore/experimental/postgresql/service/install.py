# Copyright (c) 2013 OpenStack Foundation
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

from oslo_log import log as logging

from trove.common import cfg
from trove.common.i18n import _
from trove.guestagent.datastore.experimental.postgresql.service.process import(
    PgSqlProcess)
from trove.guestagent import pkg

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PgSqlInstall(PgSqlProcess):
    """Mixin class that provides a PgSql installer.

    This mixin has a dependency on the PgSqlProcess mixin.
    """

    def __init__(self, *args, **kwargs):
        super(PgSqlInstall, self).__init__(*args, **kwargs)

    def install(self, context, packages):
        """Install one or more packages that postgresql needs to run.

        The packages parameter is a string representing the package names that
        should be given to the system's package manager.
        """

        LOG.debug(
            "{guest_id}: Beginning PgSql package installation.".format(
                guest_id=CONF.guest_id
            )
        )
        packager = pkg.Package()
        if not packager.pkg_is_installed(packages):
            try:
                LOG.info(
                    _("{guest_id}: Installing ({packages}).").format(
                        guest_id=CONF.guest_id,
                        packages=packages,
                    )
                )
                packager.pkg_install(packages, {}, 1000)
            except (pkg.PkgAdminLockError, pkg.PkgPermissionError,
                    pkg.PkgPackageStateError, pkg.PkgNotFoundError,
                    pkg.PkgTimeout, pkg.PkgScriptletError,
                    pkg.PkgDownloadError, pkg.PkgSignError,
                    pkg.PkgBrokenError):
                LOG.exception(
                    "{guest_id}: There was a package manager error while "
                    "trying to install ({packages}).".format(
                        guest_id=CONF.guest_id,
                        packages=packages,
                    )
                )
                raise
            except Exception:
                LOG.exception(
                    "{guest_id}: The package manager encountered an unknown "
                    "error while trying to install ({packages}).".format(
                        guest_id=CONF.guest_id,
                        packages=packages,
                    )
                )
                raise
            else:
                self.start_db(context)
                LOG.debug(
                    "{guest_id}: Completed package installation.".format(
                        guest_id=CONF.guest_id,
                    )
                )
