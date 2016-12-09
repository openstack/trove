# Copyright 2014 OpenStack Foundation
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


# NOTE(esp): This code was taken from nova

__all__ = [
    'init',
    'cleanup',
    'set_defaults',
    'add_extra_exmods',
    'clear_extra_exmods',
    'get_allowed_exmods',
    'get_client',
    'get_server',
    'get_notifier',
]


from oslo_config import cfg
import oslo_messaging as messaging

import trove.common.exception
from trove.common.rpc import secure_serializer as ssz
from trove.common.rpc import serializer as sz

CONF = cfg.CONF
TRANSPORT = None
NOTIFIER = None

ALLOWED_EXMODS = [
    trove.common.exception.__name__,
]

EXTRA_EXMODS = []


def init(conf):
    global TRANSPORT, NOTIFIER
    exmods = get_allowed_exmods()
    TRANSPORT = messaging.get_transport(conf,
                                        allowed_remote_exmods=exmods)

    serializer = sz.TroveRequestContextSerializer(
        messaging.JsonPayloadSerializer())
    NOTIFIER = messaging.Notifier(TRANSPORT, serializer=serializer)


def cleanup():
    global TRANSPORT, NOTIFIER
    assert TRANSPORT is not None
    assert NOTIFIER is not None
    TRANSPORT.cleanup()
    TRANSPORT = NOTIFIER = None


def set_defaults(control_exchange):
    messaging.set_transport_defaults(control_exchange)


def add_extra_exmods(*args):
    EXTRA_EXMODS.extend(args)


def clear_extra_exmods():
    del EXTRA_EXMODS[:]


def get_allowed_exmods():
    return ALLOWED_EXMODS + EXTRA_EXMODS


def get_transport_url(url_str=None):
    return messaging.TransportURL.parse(CONF, url_str)


def get_client(target, key, version_cap=None, serializer=None,
               secure_serializer=ssz.SecureSerializer):
    assert TRANSPORT is not None
    # BUG(1650518): Cleanup in the Pike release
    # uncomment this (following) line in the pike release
    # assert key is not None
    serializer = secure_serializer(
        sz.TroveRequestContextSerializer(serializer), key)
    return messaging.RPCClient(TRANSPORT,
                               target,
                               version_cap=version_cap,
                               serializer=serializer)


def get_server(target, endpoints, key, serializer=None,
               secure_serializer=ssz.SecureSerializer):
    assert TRANSPORT is not None

    # Thread module is not monkeypatched if remote debugging is enabled.
    # Using eventlet executor without monkepatching thread module will
    # lead to unpredictable results.
    from trove.common import debug_utils
    debug_utils.setup()

    executor = "blocking" if debug_utils.enabled() else "eventlet"

    # BUG(1650518): Cleanup in the Pike release
    # uncomment this (following) line in the pike release
    # assert key is not None
    serializer = secure_serializer(
        sz.TroveRequestContextSerializer(serializer), key)

    return messaging.get_rpc_server(TRANSPORT,
                                    target,
                                    endpoints,
                                    executor=executor,
                                    serializer=serializer)


def get_notifier(service=None, host=None, publisher_id=None):
    assert NOTIFIER is not None
    if not publisher_id:
        publisher_id = "%s.%s" % (service, host or CONF.host)
    return NOTIFIER.prepare(publisher_id=publisher_id)
