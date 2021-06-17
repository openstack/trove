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
import re

import docker
from oslo_log import log as logging
from oslo_utils import encodeutils

from trove.common import cfg

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
    except docker.errors.NotFound:
        LOG.info(
            f"Creating docker container, image: {image}, "
            f"volumes: {volumes}, ports: {ports}, user: {user}, "
            f"network_mode: {network_mode}, environment: {environment}, "
            f"command: {command}")
        container = client.containers.run(
            image,
            name=name,
            restart_policy={"Name": restart_policy},
            privileged=False,
            network_mode=network_mode,
            detach=True,
            volumes=volumes,
            ports=ports,
            user=user,
            environment=environment,
            command=command
        )

    return container


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
