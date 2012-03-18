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

"""
Set of utilities for the Guest Manager
"""

import fcntl
import socket
import struct


from nova import context
from nova import flags
from reddwarf.db import db_api as dbapi
# from nova.db import api as dbapi


flags.DEFINE_string('guest_ethernet_device', "eth0",
                    'Default Ethernet device for the guest agent')
FLAGS = flags.FLAGS


instance_id = None


def get_instance_id():
    """Return the instance id for this guest"""
    global instance_id
    if not instance_id:
        # TODO(rnirmal): Better way to get the instance id
        address = get_ipv4_address()
        instance = dbapi.instance_get_by_fixed_ip(context.get_admin_context(),
                                                  address)
        instance_id = instance.id
    return instance_id


def get_ipv4_address():
    """ Get the ip address provided an ethernet device"""
    # Create an IPV4 (AF_INET) datagram socket
    soc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # fcntl is a system fuction that takes in the socket file descriptor,
    # 0x8915 = SIOCGIFADDR which is an os call passed to ioctl which returns
    # the list of interface addresses.
    # struct.pack, packs the ethernet device string into a binary buffer
    return socket.inet_ntoa(fcntl.ioctl(soc.fileno(), 0x8915,
                                        struct.pack('256s',
                                        FLAGS.guest_ethernet_device[:15])
                                        )[20:24])
