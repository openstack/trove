# Copyright (c) 2011 OpenStack Foundation
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

import os

import netifaces
from trove.common import utils

REDHAT = 'redhat'
DEBIAN = 'debian'
SUSE = 'suse'


def get_os():
    if os.path.isfile("/etc/redhat-release"):
        return REDHAT
    elif os.path.isfile("/etc/SuSE-release"):
        return SUSE
    else:
        return DEBIAN


def file_discovery(file_candidates):
    for file in file_candidates:
        if os.path.isfile(file):
            return file


def service_discovery(service_candidates):
    """
    This function discovering how to start, stop, enable, disable service
    in current environment. "service_candidates" is array with possible
    system service names. Works for upstart, systemd, sysvinit.
    """
    result = {}
    for service in service_candidates:
        # check upstart
        if os.path.isfile("/etc/init/%s.conf" % service):
            # upstart returns error code when service already started/stopped
            result['cmd_start'] = "sudo start %s || true" % service
            result['cmd_stop'] = "sudo stop %s || true" % service
            result['cmd_enable'] = ("sudo sed -i '/^manual$/d' "
                                    "/etc/init/%s.conf" % service)
            result['cmd_disable'] = ("sudo sh -c 'echo manual >> "
                                     "/etc/init/%s.conf'" % service)
            break
        # check sysvinit
        if os.path.isfile("/etc/init.d/%s" % service):
            result['cmd_start'] = "sudo service %s start" % service
            result['cmd_stop'] = "sudo service %s stop" % service
            if os.path.isfile("/usr/sbin/update-rc.d"):
                result['cmd_enable'] = "sudo update-rc.d %s defaults; sudo " \
                                       "update-rc.d %s enable" % (service,
                                                                  service)
                result['cmd_disable'] = "sudo update-rc.d %s defaults; sudo " \
                                        "update-rc.d %s disable" % (service,
                                                                    service)
            elif os.path.isfile("/sbin/chkconfig"):
                result['cmd_enable'] = "sudo chkconfig %s on" % service
                result['cmd_disable'] = "sudo chkconfig %s off" % service
            break
        # check systemd
        service_path = "/lib/systemd/system/%s.service" % service
        if os.path.isfile(service_path):
            result['cmd_start'] = "sudo systemctl start %s" % service
            result['cmd_stop'] = "sudo systemctl stop %s" % service

            # currently "systemctl enable" doesn't work for symlinked units
            # as described in https://bugzilla.redhat.com/1014311, therefore
            # replacing a symlink with its real path
            if os.path.islink(service_path):
                real_path = os.path.realpath(service_path)
                unit_file_name = os.path.basename(real_path)
                result['cmd_enable'] = ("sudo systemctl enable %s" %
                                        unit_file_name)
                result['cmd_disable'] = ("sudo systemctl disable %s" %
                                         unit_file_name)
            else:
                result['cmd_enable'] = "sudo systemctl enable %s" % service
                result['cmd_disable'] = "sudo systemctl disable %s" % service
            break
    return result


def get_ip_address(ifname='eth0', address_family=netifaces.AF_INET):
    """

    Retrieves IP address which assigned to given network interface. As
    an interface can have multiple addresses associated with it, the
    address_family identifies which address is sought. By default
    this routine returns the AF_INET address.

    @parameter ifname network interface (ethX, wlanX, etc.)
    @parameter address_family the address family being sought
    """
    addresses_by_family = netifaces.ifaddresses(ifname)[address_family]
    return addresses_by_family.pop()['addr']


def update_owner(user, group, path):
    """
       Changes the owner and group for the path (recursively)
    """
    utils.execute_with_timeout("chown", "-R", "%s:%s" % (user, group), path,
                               run_as_root=True, root_helper="sudo")
