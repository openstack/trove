# Copyright 2014 Tesora Inc.
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

"""
Tests database migration scripts for mysql.

To run the tests, you'll need to set up db user named 'openstack_citest'
with password 'openstack_citest' on localhost. This user needs db
admin rights (i.e. create/drop database)

"""
import glob
import os

import migrate.versioning.api as migration_api
from migrate.versioning import repository
from oslo_concurrency import processutils
from oslo_log import log as logging
from proboscis import after_class
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import before_class
from proboscis import SkipTest
from proboscis import test
import sqlalchemy
import sqlalchemy.exc

from trove.common.i18n import _
import trove.db.sqlalchemy.migrate_repo
from trove.tests.util import event_simulator

GROUP = "dbaas.db.migrations"
LOG = logging.getLogger(__name__)


@test(groups=[GROUP])
class ProjectTestCase(object):
    """Test migration scripts integrity."""

    @test
    def test_all_migrations_have_downgrade(self):
        topdir = os.path.normpath(os.path.join(os.path.dirname(__file__),
                                  os.pardir, os.pardir, os.pardir))
        py_glob = os.path.join(topdir, "trove", "db", "sqlalchemy",
                               "migrate_repo", "versions", "*.py")

        downgrades_found = []
        for path in glob.iglob(py_glob):
            has_downgrade = False
            with open(path, "r") as f:
                for line in f:
                    if 'def downgrade(' in line:
                        has_downgrade = True

                if has_downgrade:
                    fname = os.path.basename(path)
                    downgrades_found.append(fname)

        helpful_msg = (_("The following migration scripts have a "
                         "downgrade implementation:\n\t%s") %
                       '\n\t'.join(sorted(downgrades_found)))
        assert_equal(downgrades_found, [], helpful_msg)


@test(depends_on_classes=[ProjectTestCase],
      groups=[GROUP])
class TestTroveMigrations(object):
    """Test sqlalchemy-migrate migrations."""
    USER = "openstack_citest"
    PASSWD = "openstack_citest"
    DATABASE = "openstack_citest"

    @before_class
    def setUp(self):
        event_simulator.allowable_empty_sleeps = 1

    @after_class
    def tearDown(self):
        event_simulator.allowable_empty_sleeps = 0

    def __init__(self):
        self.MIGRATE_FILE = trove.db.sqlalchemy.migrate_repo.__file__
        self.REPOSITORY = repository.Repository(
            os.path.abspath(os.path.dirname(self.MIGRATE_FILE)))
        self.INIT_VERSION = 0

    def _get_connect_string(self, backend, database=None):
        """Get database connection string."""
        args = {'backend': backend,
                'user': self.USER,
                'passwd': self.PASSWD}
        template = "%(backend)s://%(user)s:%(passwd)s@localhost"
        if database is not None:
            args['database'] = database
            template += "/%(database)s"
        return template % args

    def _is_backend_avail(self, backend):
        """Check database backend availability."""
        connect_uri = self._get_connect_string(backend)
        engine = sqlalchemy.create_engine(connect_uri)
        try:
            connection = engine.connect()
        except Exception:
            # any error here means the database backend is not available
            return False
        else:
            connection.close()
            return True
        finally:
            if engine is not None:
                engine.dispose()

    def _execute_cmd(self, cmd=None):
        """Shell out and run the given command."""
        out, err = processutils.trycmd(cmd, shell=True)
        # Until someone wants to rewrite this to avoid the warning
        # we need to handle it for newer versions of mysql
        valid_err = err == '' or \
            err == 'mysql: [Warning] Using a password on the ' \
                   'command line interface can be insecure.\n'
        assert_true(valid_err,
                    "Failed to run: '%(cmd)s' "
                    "Output: '%(stdout)s' "
                    "Error: '%(stderr)s'" %
                    {'cmd': cmd, 'stdout': out, 'stderr': err})

    def _reset_mysql(self):
        """Reset the MySQL test database

        Drop the MySQL test database if it already exists and create
        a new one.
        """
        sql = ("drop database if exists %(database)s; "
               "create database %(database)s;" % {'database': self.DATABASE})
        cmd = ("mysql -u \"%(user)s\" -p%(password)s -h %(host)s "
               "-e \"%(sql)s\"" % {'user': self.USER, 'password': self.PASSWD,
                                   'host': 'localhost', 'sql': sql})
        self._execute_cmd(cmd)

    @test
    def test_mysql_migration(self):
        db_backend = "mysql+pymysql"
        # Gracefully skip this test if the developer do not have
        # MySQL running. MySQL should always be available on
        # the infrastructure
        if not self._is_backend_avail(db_backend):
            raise SkipTest("MySQL is not available.")
        self._reset_mysql()
        connect_string = self._get_connect_string(db_backend, self.DATABASE)
        engine = sqlalchemy.create_engine(connect_string)
        self._walk_versions(engine)
        engine.dispose()

    def _walk_versions(self, engine=None):
        """Walk through and test the migration scripts

        Determine latest version script from the repo, then
        upgrade from 1 through to the latest.
        """
        # Place the database under version control
        migration_api.version_control(engine, self.REPOSITORY,
                                      self.INIT_VERSION)
        assert_equal(self.INIT_VERSION,
                     migration_api.db_version(engine, self.REPOSITORY))

        LOG.debug('Latest version is %s', self.REPOSITORY.latest)
        versions = range(self.INIT_VERSION + 1, self.REPOSITORY.latest + 1)

        # Walk from version 1 to the latest, testing the upgrade paths.
        for version in versions:
            self._migrate_up(engine, version)

    def _migrate_up(self, engine, version):
        """Migrate up to a new version of database."""
        migration_api.upgrade(engine, self.REPOSITORY, version)
        assert_equal(version,
                     migration_api.db_version(engine, self.REPOSITORY))
