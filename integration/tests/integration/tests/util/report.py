"""Creates a report for the test.
"""

import os
import shutil
from os import path
from trove.tests.config import CONFIG

USE_LOCAL_OVZ = CONFIG.use_local_ovz


class Reporter(object):
    """Saves the logs from a test run."""

    def __init__(self, root_path):
        self.root_path = root_path
        if not path.exists(self.root_path):
            os.mkdir(self.root_path)
        for file in os.listdir(self.root_path):
            if file.endswith(".log"):
                os.remove(path.join(self.root_path, file))

    def _find_all_instance_ids(self):
        instances = []
        if USE_LOCAL_OVZ:
            for dir in os.listdir("/var/lib/vz/private"):
                instances.append(dir)
        return instances

    def log(self, msg):
        with open("%s/report.log" % self.root_path, 'a') as file:
            file.write(str(msg) + "\n")

    def _save_syslog(self):
        try:
            shutil.copyfile("/var/log/syslog", "host-syslog.log")
        except (shutil.Error, IOError) as err:
            self.log("ERROR logging syslog : %s" % (err))

    def _update_instance(self, id):
        root = "%s/%s" % (self.root_path, id)

        def save_file(path, short_name):
            if USE_LOCAL_OVZ:
                try:
                    shutil.copyfile("/var/lib/vz/private/%s/%s" % (id, path),
                                    "%s-%s.log" % (root, short_name))
                except (shutil.Error, IOError) as err:
                    self.log("ERROR logging %s for instance id %s! : %s"
                             % (path, id, err))
            else:
                #TODO: Can we somehow capture these (maybe SSH to the VM)?
                pass

        save_file("/var/log/firstboot", "firstboot")
        save_file("/var/log/syslog", "syslog")
        save_file("/var/log/nova/guest.log", "nova-guest")

    def _update_instances(self):
        for id in self._find_all_instance_ids():
            self._update_instance(id)

    def update(self):
        self._update_instances()
        self._save_syslog()


REPORTER = Reporter(CONFIG.report_directory)


def log(msg):
    REPORTER.log(msg)


def update():
    REPORTER.update()
