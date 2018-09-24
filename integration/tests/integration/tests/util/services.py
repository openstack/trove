# Copyright (c) 2011 OpenStack, LLC.
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

"""Functions to initiate and shut down services needed by the tests."""

import os
import re
import subprocess
import time

from collections import namedtuple
from httplib2 import Http
from nose.plugins.skip import SkipTest

from proboscis import decorators


def _is_web_service_alive(url):
    """Does a HTTP GET request to see if the web service is up."""
    client = Http()
    try:
        resp = client.request(url, 'GET')
        return resp != None
    except Exception:
        return False


_running_services = []


def get_running_services():
    """ Returns the list of services which this program has started."""
    return _running_services


def start_proc(cmd, shell=False):
    """Given a command, starts and returns a process."""
    env = os.environ.copy()
    proc = subprocess.Popen(
        cmd,
        shell=shell,
        stdin=subprocess.PIPE,
        bufsize=0,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    return proc


MemoryInfo = namedtuple("MemoryInfo", ['mapped', 'writeable', 'shared'])


class Service(object):
    """Starts and stops a service under test.

    The methods to start and stop the service will not actually do anything
    if they detect the service is already running on this machine.  This is
    because it may be useful for developers to start the services themselves
    some other way.

    """

    # TODO(tim.simpson): Hard to follow, consider renaming certain attributes.

    def __init__(self, cmd):
        """Defines a service to run."""
        if not isinstance(cmd, list):
            raise TypeError()
        self.cmd = cmd
        self.do_not_manage_proc = False
        self.proc = None

    def __del__(self):
        if self.is_running:
            self.stop()

    def ensure_started(self):
        """Starts the service if it is not running."""
        if not self.is_running:
            self.start()

    def find_proc_id(self):
        """Finds and returns the process id."""
        if not self.cmd:
            return False
        # The cmd[1] signifies the executable python script. It gets invoked
        # as python /path/to/executable args, so the entry is
        # /path/to/executable
        actual_command = self.cmd[1].split("/")[-1]
        proc_command = ["/usr/bin/pgrep", "-f", actual_command]
        proc = start_proc(proc_command, shell=False)
        # this is to make sure there is only one pid returned from the pgrep
        has_two_lines = False
        pid = None
        for line in iter(proc.stdout.readline, ""):
            if has_two_lines:
                raise RuntimeError("Found PID twice.")
            pid = int(line)
            has_two_lines = True
        return pid

    def get_memory_info(self):
        """Returns how much memory the process is using according to pmap."""
        pid = self.find_proc_id()
        if not pid:
            raise RuntimeError("Can't find PID, so can't get memory.")
        proc = start_proc(["/usr/bin/pmap", "-d", str(pid)],
                          shell=False)
        for line in iter(proc.stdout.readline, ""):
            m = re.search(r"mapped\:\s([0-9]+)K\s+"
                          r"writeable/private:\s([0-9]+)K\s+"
                          r"shared:\s+([0-9]+)K", line)
            if m:
                return MemoryInfo(int(m.group(1)), int(m.group(2)),
                                  int(m.group(3)))
        raise RuntimeError("Memory info not found.")

    def get_fd_count_from_proc_file(self):
        """Returns file descriptors according to /proc/<id>/status."""
        pid = self.find_proc_id()
        with open("/proc/%d/status" % pid) as status:
            for line in status.readlines():
                index = line.find(":")
                name = line[:index]
                value = line[index + 1:]
                if name == "FDSize":
                    return int(value)
        raise RuntimeError("FDSize not found!")

    def get_fd_count(self):
        """Returns file descriptors according to /proc/<id>/status."""
        pid = self.find_proc_id()
        cmd = "Finding file descriptors..."
        print("CMD" + cmd)
        proc = start_proc(['ls', '-la', '/proc/%d/fd' % pid], shell=False)
        count = -3
        has_two_lines = False
        for line in iter(proc.stdout.readline, ""):
            print("\t" + line)
            count += 1
        if not count:
            raise RuntimeError("Could not get file descriptors!")
        return count


        with open("/proc/%d/fd" % pid) as status:
            for line in status.readlines():
                index = line.find(":")
                name = line[:index]
                value = line[index + 1:]
                if name == "FDSize":
                    return int(value)
        raise RuntimeError("FDSize not found!")

    def kill_proc(self):
        """Kills the process, wherever it may be."""
        pid = self.find_proc_id()
        if pid:
            start_proc("sudo kill -9 " + str(pid), shell=True)
            time.sleep(1)
        if self.is_service_alive():
            raise RuntimeError('Cannot kill process, PID=' +
                               str(self.proc.pid))

    def is_service_alive(self, proc_name_index=1):
        """Searches for the process to see if its alive.

         This function will return true even if this class has not started
         the service (searches using ps).

         """
        if not self.cmd:
            return False
        time.sleep(1)
        # The cmd[1] signifies the executable python script. It gets invoked
        # as python /path/to/executable args, so the entry is
        # /path/to/executable
        actual_command = self.cmd[proc_name_index].split("/")[-1]
        print(actual_command)
        proc_command = ["/usr/bin/pgrep", "-f", actual_command]
        print(proc_command)
        proc = start_proc(proc_command, shell=False)
        line = proc.stdout.readline()
        print(line)
        # pgrep only returns a pid. if there is no pid, it'll return nothing
        return len(line) != 0

    @property
    def is_running(self):
        """Returns true if the service has already been started.

        Returns true if this program has started the service or if it
        previously detected it had started.  The main use of this property
        is to know if the service was already begun by this program-
        use is_service_alive for a more definitive answer.

        """
        return self.proc or self.do_not_manage_proc

    def restart(self, extra_args):
        if self.do_not_manage_proc:
            raise RuntimeError("Can't restart proc as the tests don't own it.")
        self.stop()
        time.sleep(2)
        self.start(extra_args=extra_args)

    def start(self, time_out=30, extra_args=None):
        """Starts the service if necessary."""
        extra_args = extra_args or []
        if self.is_running:
            raise RuntimeError("Process is already running.")
        if self.is_service_alive():
            self.do_not_manage_proc = True
            return
        self.proc = start_proc(self.cmd + extra_args, shell=False)
        if not self._wait_for_start(time_out=time_out):
            self.stop()
            raise RuntimeError("Issued the command successfully but the "
                               "service (" + str(self.cmd + extra_args) +
                               ") never seemed to start.")
        _running_services.append(self)

    def stop(self):
        """Stops the service, but only if this program started it."""
        if self.do_not_manage_proc:
            return
        if not self.proc:
            raise RuntimeError("Process was not started.")
        self.proc.terminate()
        self.proc.kill()
        self.proc.wait()
        self.proc.stdin.close()
        self.kill_proc()
        self.proc = None
        global _running_services
        _running_services = [svc for svc in _running_services if svc != self]

    def _wait_for_start(self, time_out):
        """Waits until time_out (in seconds) for service to appear."""
        give_up_time = time.time() + time_out
        while time.time() < give_up_time:
            if self.is_service_alive():
                return True
        return False


class NativeService(Service):

    def is_service_alive(self):
        return super(NativeService, self).is_service_alive(proc_name_index=0)



class WebService(Service):
    """Starts and stops a web service under test."""

    def __init__(self, cmd, url):
        """Defines a service to run."""
        Service.__init__(self, cmd)
        if not isinstance(url, (str, unicode)):
            raise TypeError()
        self.url = url
        self.do_not_manage_proc = self.is_service_alive()

    def is_service_alive(self):
        """Searches for the process to see if its alive."""
        return _is_web_service_alive(self.url)
