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
from unittest import mock

from trove.guestagent.utils import docker as docker_utils
from trove.tests.unittests import trove_testtools


class TestDockerUtils(trove_testtools.TestCase):
    def setUp(self):
        super().setUp()
        self.docker_client = mock.MagicMock()

    def test_create_network_with_network_exists(self):
        network_name = "test_network"
        network1 = mock.MagicMock(id="111")
        network1.name = "test_network"
        network2 = mock.MagicMock(id="222")
        network2.name = "test_network_2"
        self.docker_client.networks.list.return_value = [network1, network2]
        id = docker_utils.create_network(self.docker_client, network_name)
        self.assertEqual(id, "111")

    def test_create_network_ipv4_only(self):
        network_name = "test_network"
        eth1_data = json.dumps({"mac_address": "fa:16:3e:7c:9c:57",
                                "ipv4_address": "10.111.0.8",
                                "ipv4_cidr": "10.111.0.0/26",
                                "ipv4_gateway": "10.111.0.1",
                                "ipv4_host_routes": [{
                                    "destination": "10.10.0.0/16",
                                    "nexthop": "10.111.0.10"}]})
        net = mock.MagicMock(return_value=mock.MagicMock(id=111))
        self.docker_client.networks.create = net
        mo = mock.mock_open(read_data=eth1_data)
        with mock.patch.object(docker_utils, 'open', mo):
            id = docker_utils.create_network(self.docker_client, network_name)
        self.assertEqual(id, 111)
        net.assert_called_once()
        kwargs = net.call_args.kwargs
        self.assertEqual(kwargs.get("name"), "test_network")
        self.assertEqual(kwargs.get("driver"), "docker-hostnic")
        self.assertEqual(len(kwargs.get("ipam").get("Config")), 1)
        self.assertEqual(kwargs["ipam"]["Config"][0]["Gateway"],
                         "10.111.0.1")
        self.assertEqual(kwargs["enable_ipv6"], False)
        self.assertEqual(kwargs["options"]["hostnic_mac"],
                         "fa:16:3e:7c:9c:57")

    def test_create_network_ipv6_only(self):
        network_name = "test_network"
        eth1_data = json.dumps({"mac_address": "fa:16:3e:7c:9c:58",
                                "ipv6_address":
                                    "fda3:96d9:23e:0:f816:3eff:fe7c:9c57",
                                "ipv6_cidr": "fda3:96d9:23e::/64",
                                "ipv6_gateway": "fda3:96d9:23e::1"})
        net = mock.MagicMock(return_value=mock.MagicMock(id=222))
        self.docker_client.networks.create = net
        mo = mock.mock_open(read_data=eth1_data)
        with mock.patch.object(docker_utils, 'open', mo):
            id = docker_utils.create_network(self.docker_client, network_name)
        self.assertEqual(id, 222)
        net.assert_called_once()
        kwargs = net.call_args.kwargs
        self.assertEqual(kwargs.get("name"), "test_network")
        self.assertEqual(kwargs.get("driver"), "docker-hostnic")
        self.assertEqual(len(kwargs.get("ipam").get("Config")), 1)
        self.assertEqual(kwargs["ipam"]["Config"][0]["Gateway"],
                         "fda3:96d9:23e::1")
        self.assertEqual(kwargs["enable_ipv6"], True)
        self.assertEqual(kwargs["options"]["hostnic_mac"], "fa:16:3e:7c:9c:58")

    def test_create_network_dual_stack(self):
        network_name = "test_network"
        eth1_data = json.dumps({"mac_address": "fa:16:3e:7c:9c:59",
                                "ipv4_address": "10.111.0.8",
                                "ipv4_cidr": "10.111.0.0/26",
                                "ipv4_gateway": "10.111.0.1",
                                "ipv4_host_routes": [{
                                    "destination": "10.10.0.0/16",
                                    "nexthop": "10.111.0.10"}],
                                "ipv6_address":
                                    "fda3:96d9:23e:0:f816:3eff:fe7c:9c57",
                                "ipv6_cidr": "fda3:96d9:23e::/64",
                                "ipv6_gateway": "fda3:96d9:23e::1"})
        net = mock.MagicMock(return_value=mock.MagicMock(id=333))
        self.docker_client.networks.create = net
        mo = mock.mock_open(read_data=eth1_data)
        with mock.patch.object(docker_utils, 'open', mo):
            id = docker_utils.create_network(self.docker_client, network_name)
        self.assertEqual(id, 333)
        net.assert_called_once()
        kwargs = net.call_args.kwargs
        self.assertEqual(kwargs["name"], "test_network")
        self.assertEqual(kwargs["driver"], "docker-hostnic")
        self.assertEqual(len(kwargs["ipam"]["Config"]), 2)
        self.assertEqual(kwargs["enable_ipv6"], True)
        self.assertEqual(kwargs["options"]["hostnic_mac"],
                         "fa:16:3e:7c:9c:59")

    @mock.patch("docker.APIClient")
    def test__create_container_with_low_level_api(self, mock_client):
        eth1_data = json.dumps({
            "mac_address": "fa:16:3e:7c:9c:57",
            "ipv4_address": "10.111.0.8",
            "ipv4_cidr": "10.111.0.0/26",
            "ipv4_gateway": "10.111.0.1",
            "ipv4_host_routes": [{"destination": "10.10.0.0/16",
                                  "nexthop": "10.111.0.10"}]})

        mo = mock.mock_open(read_data=eth1_data)
        param = dict(name="test",
                     restart_policy={"Name": "always"},
                     privileged=False,
                     detach=True,
                     volumes={},
                     ports={},
                     user="test_user",
                     environment={},
                     command="sleep inf")
        with mock.patch.object(docker_utils, 'open', mo):
            docker_utils._create_container_with_low_level_api(
                "busybox", param)
        mock_client().create_host_config.assert_called_once()
        mock_client().create_networking_config.assert_called_once()
        mock_client().pull.assert_called_once()
        mock_client().create_container.assert_called_once()
        mock_client().start.assert_called_once()
