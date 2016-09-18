# Copyright (c) 2014 eBay Software Foundation
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
#

import json
import os.path
import time

from oslo_log import log as logging

from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.couchbase import service
from trove.guestagent.datastore.experimental.couchbase import system
from trove.guestagent.strategies.restore import base


LOG = logging.getLogger(__name__)


class CbBackup(base.RestoreRunner):
    """
    Implementation of Restore Strategy for Couchbase.
    """
    __strategy_name__ = 'cbbackup'
    base_restore_cmd = 'sudo tar xpPf -'

    def __init__(self, *args, **kwargs):
        super(CbBackup, self).__init__(*args, **kwargs)

    def pre_restore(self):
        try:
            operating_system.remove(system.COUCHBASE_DUMP_DIR, force=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error during pre-restore phase."))
            raise

    def post_restore(self):
        try:
            # Root enabled for the backup
            pwd_file = system.COUCHBASE_DUMP_DIR + system.SECRET_KEY
            if os.path.exists(pwd_file):
                with open(pwd_file, "r") as f:
                    pw = f.read().rstrip("\n")
                    root = service.CouchbaseRootAccess()
                    root.set_password(pw)

            # Get current root password
            root = service.CouchbaseRootAccess()
            root_pwd = root.get_password()

            # Iterate through each bucket config
            buckets_json = system.COUCHBASE_DUMP_DIR + system.BUCKETS_JSON
            with open(buckets_json, "r") as f:
                out = f.read()
                if out == "[]":
                    # No buckets or data to restore. Done.
                    return
                d = json.loads(out)
                for i in range(len(d)):
                    bucket_name = d[i]["name"]
                    bucket_type = d[i]["bucketType"]
                    if bucket_type == "membase":
                        bucket_type = "couchbase"
                    ram = int(utils.to_mb(d[i]["quota"]["ram"]))
                    auth_type = d[i]["authType"]
                    password = d[i]["saslPassword"]
                    port = d[i]["proxyPort"]
                    replica_number = d[i]["replicaNumber"]
                    replica_index = 1 if d[i]["replicaIndex"] else 0
                    threads = d[i]["threadsNumber"]
                    flush = 1 if "flush" in d[i]["controllers"] else 0

                    # cbrestore requires you to manually create dest buckets
                    create_bucket_cmd = ('curl -X POST -u root:' + root_pwd +
                                         ' -d name="' +
                                         bucket_name + '"' +
                                         ' -d bucketType="' +
                                         bucket_type + '"' +
                                         ' -d ramQuotaMB="' +
                                         str(ram) + '"' +
                                         ' -d authType="' +
                                         auth_type + '"' +
                                         ' -d saslPassword="' +
                                         password + '"' +
                                         ' -d proxyPort="' +
                                         str(port) + '"' +
                                         ' -d replicaNumber="' +
                                         str(replica_number) + '"' +
                                         ' -d replicaIndex="' +
                                         str(replica_index) + '"' +
                                         ' -d threadsNumber="' +
                                         str(threads) + '"' +
                                         ' -d flushEnabled="' +
                                         str(flush) + '" ' +
                                         system.COUCHBASE_REST_API +
                                         '/pools/default/buckets')
                    utils.execute_with_timeout(create_bucket_cmd,
                                               shell=True, timeout=300)

                    if bucket_type == "memcached":
                        continue

                    # Wait for couchbase (membase) bucket creation to complete
                    # (follows same logic as --wait for couchbase-cli)
                    timeout_in_seconds = 120
                    start = time.time()
                    bucket_exist = False
                    while ((time.time() - start) <= timeout_in_seconds and
                            not bucket_exist):
                        url = (system.COUCHBASE_REST_API +
                               '/pools/default/buckets/')
                        outfile = system.COUCHBASE_DUMP_DIR + '/buckets.all'
                        utils.execute_with_timeout('curl -u root:' + root_pwd +
                                                   ' ' + url + ' > ' + outfile,
                                                   shell=True, timeout=300)
                        with open(outfile, "r") as file:
                            out = file.read()
                            buckets = json.loads(out)
                            for bucket in buckets:
                                if bucket["name"] == bucket_name:
                                    bucket_exist = True
                                    break
                        if not bucket_exist:
                            time.sleep(2)

                    if not bucket_exist:
                        raise base.RestoreError("Failed to create bucket '%s' "
                                                "within %s seconds"
                                                % (bucket_name,
                                                   timeout_in_seconds))

                    # Query status
                    # (follows same logic as --wait for couchbase-cli)
                    healthy = False
                    while ((time.time() - start) <= timeout_in_seconds):
                        url = (system.COUCHBASE_REST_API +
                               '/pools/default/buckets/' +
                               bucket_name)
                        outfile = system.COUCHBASE_DUMP_DIR + '/' + bucket_name
                        utils.execute_with_timeout('curl -u root:' + root_pwd +
                                                   ' ' + url + ' > ' + outfile,
                                                   shell=True, timeout=300)
                        all_node_ready = True
                        with open(outfile, "r") as file:
                            out = file.read()
                            bucket = json.loads(out)
                            for node in bucket["nodes"]:
                                if node["status"] != "healthy":
                                    all_node_ready = False
                                    break
                        if not all_node_ready:
                            time.sleep(2)
                        else:
                            healthy = True
                            break

                    if not healthy:
                        raise base.RestoreError("Bucket '%s' is created but "
                                                "not ready to use within %s "
                                                "seconds"
                                                % (bucket_name,
                                                   timeout_in_seconds))

                    # Restore
                    restore_cmd = ('/opt/couchbase/bin/cbrestore ' +
                                   system.COUCHBASE_DUMP_DIR + ' ' +
                                   system.COUCHBASE_REST_API +
                                   ' --bucket-source=' + bucket_name +
                                   ' --bucket-destination=' + bucket_name +
                                   ' -u root' + ' -p ' + root_pwd)
                    try:
                        utils.execute_with_timeout(restore_cmd,
                                                   shell=True,
                                                   timeout=300)
                    except exception.ProcessExecutionError:
                        # cbrestore fails or hangs at times:
                        # http://www.couchbase.com/issues/browse/MB-10832
                        # Retrying typically works
                        LOG.exception(_("cbrestore failed. Retrying..."))
                        utils.execute_with_timeout(restore_cmd,
                                                   shell=True,
                                                   timeout=300)
        except exception.ProcessExecutionError as p:
            LOG.error(p)
            raise base.RestoreError("Couchbase restore failed.")
