# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
import json
import re

import docker
from docker import errors as derros
from docker import types
from oslo_log import log as logging
from oslo_utils import encodeutils

from trove.common import cfg
from trove.common import constants

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')


def stop_container(client, name="database"):
    try:
        container = client.containers.get(name)
    except docker.errors.NotFound:
        LOG.warning("Failed to get container %s", name)
        return

    container.stop(timeout=CONF.state_change_wait_time)


def create_network(client: docker.client.DockerClient,
                   name: str) -> str:
    networks = client.networks.list()
    for net in networks:
        if net.name == name:
            return net.id
    LOG.debug("Creating docker network: %s", name)
    with open(constants.ETH1_CONFIG_PATH) as fd:
        eth1_config = json.load(fd)
    enable_ipv6 = False
    ipam_pool = list()
    if eth1_config.get("ipv4_address"):
        ipam_pool.append(types.IPAMPool(
            subnet=eth1_config.get("ipv4_cidr"),
            gateway=eth1_config.get("ipv4_gateway"))
        )
    if eth1_config.get("ipv6_address"):
        enable_ipv6 = True
        ipam_pool.append(types.IPAMPool(
            subnet=eth1_config.get("ipv6_cidr"),
            gateway=eth1_config.get("ipv6_gateway")
        ))

    ipam_config = docker.types.IPAMConfig(pool_configs=ipam_pool)
    mac_address = eth1_config.get("mac_address")
    net = client.networks.create(name=name,
                                 driver=constants.DOCKER_HOST_NIC_MODE,
                                 ipam=ipam_config,
                                 enable_ipv6=enable_ipv6,
                                 options=dict(hostnic_mac=mac_address))
    LOG.debug("docker network: %s created successfully", net.id)
    return net.id


def _create_container_with_low_level_api(image: str, param: dict) -> None:
    # create a low-level docker api object
    client = docker.APIClient(base_url='unix://var/run/docker.sock')
    host_config_kwargs = dict()
    if param.get("restart_policy"):
        host_config_kwargs["restart_policy"] = param.get("restart_policy")
    if param.get("privileged"):
        host_config_kwargs["privileged"] = param.get("privileged")
    if param.get("volumes"):
        host_config_kwargs["binds"] = param.get("volumes")
    host_config = client.create_host_config(**host_config_kwargs)

    network_config_kwargs = dict()
    with open(constants.ETH1_CONFIG_PATH) as fd:
        eth1_config = json.load(fd)
    if eth1_config.get("ipv4_address"):
        network_config_kwargs["ipv4_address"] = eth1_config.get("ipv4_address")
    if eth1_config.get("ipv6_address"):
        network_config_kwargs["ipv6_address"] = eth1_config.get("ipv6_address")

    networking_config = client.create_networking_config(
        {param.get("network"):
            client.create_endpoint_config(**network_config_kwargs)})
    # NOTE(wuchunyang): the low-level api doesn't support RUN interface,
    # so we need pull image first, then start the container
    LOG.debug("Pulling docker images: %s", image)
    try:
        client.pull(image)
    except derros.APIError as e:
        LOG.error("failed to pull image: %s, due to the error: %s", image, e)
        raise
    LOG.debug("Creating container: %s", param.get("name"))
    container = client.create_container(image=image,
                                        name=param.get("name"),
                                        detach=param.get("detach"),
                                        user=param.get("user"),
                                        environment=param.get("environment"),
                                        command=param.get("command"),
                                        host_config=host_config,
                                        networking_config=networking_config)
    LOG.debug("Starting container: %s", param.get("name"))
    client.start(container=container)


def start_container(client, image, name="database",
                    restart_policy="unless-stopped",
                    volumes={}, ports={}, user="", network_mode="host",
                    environment={}, command=""):
    """Start a docker container.

    :param client: docker client obj.
    :param image: docker image.
    :param name: container name.
    :param restart_policy: restart policy.
    :param volumes: e.g.
           {"/host/trove": {"bind": "/container/trove", "mode": "rw"}}
    :param ports: ports is ignored when network_mode="host". e.g.
           {"3306/tcp": 3306}
    :param user: e.g. "1000.1001"
    :param network_mode: One of bridge, none, host
    :param environment: Environment variables
    :param command:
    :return:
    """
    try:
        container = client.containers.get(name)
        LOG.info(f'Starting existing container {name}')
        container.start()
        return
    except docker.errors.NotFound:
        pass

    LOG.info(
        f"Creating docker container, image: {image}, "
        f"volumes: {volumes}, ports: {ports}, user: {user}, "
        f"network_mode: {network_mode}, environment: {environment}, "
        f"command: {command}")
    kwargs = dict(name=name,
                  restart_policy={"Name": restart_policy},
                  privileged=False,
                  detach=True,
                  volumes=volumes,
                  ports=ports,
                  user=user,
                  environment=environment,
                  command=command)
    if network_mode == constants.DOCKER_HOST_NIC_MODE:
        create_network(client, constants.DOCKER_NETWORK_NAME)
        kwargs["network"] = constants.DOCKER_NETWORK_NAME
        return _create_container_with_low_level_api(image, kwargs)
    else:
        kwargs["network_mode"] = network_mode
        return client.containers.run(image, **kwargs)


def _decode_output(output):
    output = encodeutils.safe_decode(output)
    output = ANSI_ESCAPE.sub('', output.strip())
    return output.split('\n')


def run_container(client, image, name, network_mode="host", volumes={},
                  command="", user=""):
    """Run command in a container and return the string output list.

    :returns output: The log output.
    :returns ret: True if no error occurs, otherwise False.
    """
    try:
        container = client.containers.get(name)
        LOG.debug(f'Removing existing container {name}')
        container.remove(force=True)
    except docker.errors.NotFound:
        pass

    try:
        LOG.info(
            f'Running container {name}, image: {image}, '
            f'network_mode: {network_mode}, volumes: {volumes}, '
            f'command: {command}')
        output = client.containers.run(
            image,
            name=name,
            network_mode=network_mode,
            volumes=volumes,
            remove=False,
            command=command,
            user=user,
        )
    except docker.errors.ContainerError as err:
        output = err.container.logs()
        return _decode_output(output), False

    return _decode_output(output), True


def get_container_status(client, name="database"):
    try:
        container = client.containers.get(name)
        # One of created, restarting, running, removing, paused, exited, or
        # dead
        return container.status
    except docker.errors.NotFound:
        return "not running"
    except Exception:
        return "unknown"


def run_command(client, command, name="database"):
    container = client.containers.get(name)
    # output is Bytes type
    ret, output = container.exec_run(command)
    if ret == 1:
        raise Exception('Running command error: %s' % output)

    return output


def restart_container(client, name="database"):
    container = client.containers.get(name)
    container.restart(timeout=CONF.state_change_wait_time)


def remove_container(client, name="database"):
    try:
        container = client.containers.get(name)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass


def get_container_logs(client, name='database', tail=50):
    container = client.containers.get(name)
    output = container.logs(tail=tail)
    return _decode_output(output)


def prune_images(client):
    """Remove unused images."""
    try:
        client.images.prune(filters={'dangling': False})
    except Exception as e:
        LOG.warning(f"Prune image failed, error: {str(e)}")
