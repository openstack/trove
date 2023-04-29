# Copyright 2023 Yovole
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

import json
import jsonschema
import netaddr
import os
import sys
import traceback

import flask
from flask import Flask
import gunicorn.app.base
from oslo_log import log as logging
from pyroute2 import IPRoute
from werkzeug import exceptions as w_exceptions

from trove.common import constants
from trove.common import schemata

LOG = logging.getLogger(__name__)


class hostnic_config(object):
    """this class records network id and its host nic"""
    CONFIG_FILE = "/etc/docker/hostnic.json"

    def __init__(self) -> None:
        if not os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, 'w+') as f:
                f.write(json.dumps({}))

    def get_data(self) -> dict:
        with open(self.CONFIG_FILE, 'r') as cfg:
            data = json.loads(cfg.read())
        return data

    def write_config(self, key: str, value: str):
        data = self.get_data()
        data[key] = value
        with open(self.CONFIG_FILE, 'w+') as cfg:
            cfg.write(json.dumps(data))

    def get_config(self, key: str):
        data = self.get_data()
        return data.get(key, "")

    def delete_config(self, key: str):
        data = self.get_data()
        if not data.get(key):
            return
        data.pop(key)
        with open(self.CONFIG_FILE, 'w+') as cfg:
            cfg.write(json.dumps(data))


driver_config = hostnic_config()


def make_json_app(import_name, **kwargs):
    """Creates a JSON-oriented Flask app.

    All error responses that you don't specifically manage yourself will have
    application/json content type, and will contain JSON that follows the
    libnetwork remote driver protocol.


    { "Err": "405: Method Not Allowed" }


    See:
      - https://github.com/docker/libnetwork/blob/3c8e06bc0580a2a1b2440fe0792fbfcd43a9feca/docs/remote.md#errors  # noqa
    """

    app = Flask(import_name)

    @app.errorhandler(jsonschema.ValidationError)
    def make_json_error(ex):
        LOG.error("Unexpected error happened: %s", ex)
        traceback.print_exc(file=sys.stderr)
        response = flask.jsonify({"Err": str(ex)})
        response.status_code = w_exceptions.InternalServerError.code
        if isinstance(ex, w_exceptions.HTTPException):
            response.status_code = ex.code
        elif isinstance(ex, jsonschema.ValidationError):
            response.status_code = w_exceptions.BadRequest.code
        content_type = 'application/vnd.docker.plugins.v1+json; charset=utf-8'
        response.headers['Content-Type'] = content_type
        return response

    for code in w_exceptions.default_exceptions:
        app.register_error_handler(code, make_json_error)

    return app


app = make_json_app(__name__)


@app.route('/Plugin.Activate', methods=['POST', 'GET'])
def plugin_activate():
    """Returns the list of the implemented drivers.

    See the following link for more details about the spec:

      https://github.com/docker/libnetwork/blob/master/docs/remote.md#handshake  # noqa
    """
    LOG.debug("Received /Plugin.Activate")
    return flask.jsonify(schemata.SCHEMA['PLUGIN_ACTIVATE'])


@app.route('/NetworkDriver.GetCapabilities', methods=['POST'])
def plugin_scope():
    """Returns the capability as the remote network driver.

    This function returns the capability of the remote network driver, which is
    ``global`` or ``local`` and defaults to ``local``. With ``global``
    capability, the network information is shared among multipe Docker daemons
    if the distributed store is appropriately configured.

    See the following link for more details about the spec:

      https://github.com/docker/libnetwork/blob/master/docs/remote.md#set-capability  # noqa
    """
    LOG.debug("Received /NetworkDriver.GetCapabilities")
    capabilities = {'Scope': 'local'}
    return flask.jsonify(capabilities)


@app.route('/NetworkDriver.DiscoverNew', methods=['POST'])
def network_driver_discover_new():
    """The callback function for the DiscoverNew notification.

    The DiscoverNew notification includes the type of the
    resource that has been newly discovered and possibly other
    information associated with the resource.

    See the following link for more details about the spec:

      https://github.com/docker/libnetwork/blob/master/docs/remote.md#discovernew-notification  # noqa
    """
    LOG.debug("Received /NetworkDriver.DiscoverNew")
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.DiscoverDelete', methods=['POST'])
def network_driver_discover_delete():
    """The callback function for the DiscoverDelete notification.

    See the following link for more details about the spec:

      https://github.com/docker/libnetwork/blob/master/docs/remote.md#discoverdelete-notification  # noqa
    """
    LOG.debug("Received /NetworkDriver.DiscoverDelete")
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.CreateNetwork', methods=['POST'])
def network_driver_create_network():
    """Creates a new  Network which name is the given NetworkID.
    example:
    docker network create --driver docker-hostnic --gateway 192.168.1.1  --subnet 192.168.1.0/24 -o hostnic_mac=52:54:00:e1:d9:ef  test_network
    See the following link for more details about the spec:

      https://github.com/docker/libnetwork/blob/master/docs/remote.md#create-network  # noqa
    """
    json_data = flask.request.get_json(force=True)
    jsonschema.validate(json_data, schemata.NETWORK_CREATE_SCHEMA)
    hostnic_mac = \
        json_data['Options']['com.docker.network.generic']['hostnic_mac']
    if driver_config.get_config(json_data['NetworkID']):
        return flask.jsonify("network already has a host nic")
    gw = json_data.get("IPv4Data")[0].get("Gateway", '')
    netinfo = {"mac_address": hostnic_mac}
    if gw:
        ip = netaddr.IPNetwork(gw)
        netinfo["gateway"] = str(ip.ip)
    driver_config.write_config(json_data['NetworkID'], netinfo)
    LOG.debug("Received JSON data %s for /NetworkDriver.Create", json_data)
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.DeleteNetwork', methods=['POST'])
def network_driver_delete_network():
    # Just remove the network from the config file.
    json_data = flask.request.get_json(force=True)
    driver_config.delete_config(json_data['NetworkID'])
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.Join', methods=['POST'])
def network_driver_join():
    json_data = flask.request.get_json(force=True)
    jsonschema.validate(json_data, schemata.NETWORK_JOIN_SCHEMA)
    netid = json_data['NetworkID']
    hostnic_mac = driver_config.get_config(netid).get('mac_address')
    ipr = IPRoute()
    ifaces = ipr.get_links(address=hostnic_mac)
    ifname = ifaces[0].get_attr('IFLA_IFNAME')
    with open(constants.ETH1_CONFIG_PATH) as fd:
        eth1_config = json.load(fd)
    join_response = {
        "InterfaceName": {
            "SrcName": ifname,
            "DstPrefix": "eth"},
    }
    if eth1_config.get("ipv4_gateway"):
        join_response["Gateway"] = eth1_config.get("ipv4_gateway")
    if eth1_config.get("ipv6_gateway"):
        join_response["GatewayIPv6"] = eth1_config.get("ipv6_gateway")
    if eth1_config.get("ipv4_host_routes"):
        join_response["StaticRoutes"] = list()
        for route in eth1_config.get("ipv4_host_routes"):
            join_response["StaticRoutes"].append(
                {"Destination": route["destination"],
                 "NextHop": route["nexthop"]})
    return flask.jsonify(join_response)


@app.route('/NetworkDriver.Leave', methods=['POST'])
def network_driver_leave():
    """Unbinds a hostnic from a sandbox.

    This function takes the following JSON data and delete the veth pair
    corresponding to the given info. ::

        {
            "NetworkID": string,
            "EndpointID": string
        }
    we don't need to remove the port from the sandbox explicitly,
    once the sandbox get deleted, the hostnic comes to default
    netns automatically.
    """
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.DeleteEndpoint', methods=['POST'])
def network_driver_delete_endpoint():
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.CreateEndpoint', methods=['POST'])
def network_driver_create_endpoint():
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.EndpointOperInfo', methods=['POST'])
def network_driver_endpoint_operational_info():
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.ProgramExternalConnectivity', methods=['POST'])
def network_driver_program_external_connectivity():
    """provide external connectivity for the given container."""
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


@app.route('/NetworkDriver.RevokeExternalConnectivity', methods=['POST'])
def network_driver_revoke_external_connectivity():
    """Removes external connectivity for a given container.

    Performs the necessary programming to remove the external connectivity
    of a container

    See the following link for more details about the spec:
      https://github.com/docker/libnetwork/blob/master/driverapi/driverapi.go
    """
    return flask.jsonify(schemata.SCHEMA['SUCCESS'])


class StandaloneApplication(gunicorn.app.base.BaseApplication):

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def main():
    options = {
        'bind': "unix:/run/docker/docker-hostnic.sock",
        'workers': 1,
    }
    StandaloneApplication(app, options).run()
