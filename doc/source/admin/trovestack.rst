..
      Copyright 2019 Catalyst IT Ltd
      All Rights Reserved.
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Trove integration script - trovestack
=====================================

``trovestack`` in ``integration/scripts`` folder is a shell script that
contains lots of useful functionalities via sub-commands including ``install``
(trove development environment installation), ``unit-tests``,  ``gate-tests``
(functional test), ``build-image``, etc. This guide introduces some of them.

Before running ``trovestack`` command, go to the scripts folder:

.. code-block:: console

    git clone https://github.com/openstack/trove
    cd trove/integration/scripts

Build guest agent image
~~~~~~~~~~~~~~~~~~~~~~~

The trove guest agent image could be created by running the following command:

.. code-block:: console

    $ ./trovestack build-image \
        ${datastore_type} \
        ${guest_os} \
        ${guest_os_release} \
        ${dev_mode}

* Currently, only ``guest_os=ubuntu`` and ``guest_os_release=xenial`` are fully
  tested and supported.

* ``dev_mode=true`` is mainly for testing purpose for trove developers and it's
  necessary to build the image on the trove controller host, because the host
  and the guest VM need to ssh into each other without password. In this mode,
  when the trove guest agent code is changed, the image doesn't need to be
  rebuilt which is convenient for debugging. Trove guest agent will ssh into
  the host and download trove code during the service initialization.

* if ``dev_mode=false``, the trove code for guest agent is injected into the
  image at the building time. Now ``dev_mode=false`` is still in experimental
  and not considered production ready yet.

* If you build the image on host1 but the trove controller service is running
  on host2, you need to set ``dev_mode=false`` and set ``CONTROLLER_IP`` as the
  IP address of trove controller service host. As the cloud administrator, you
  also need to create a Nova keypair and set ``nova_keypair`` option in Trove
  config file in order to ssh into the guest agent.

For example, in order to build a MySQL image for Ubuntu Xenial operating
system:

.. code-block:: console

    $ ./trovestack build-image mysql ubuntu xenial true

Once the image build is finished, the cloud administrator needs to register the
image in Glance and register a new datastore or version in Trove using
``trove-manage`` command, e.g. you've built an image for MySQL 5.7.1:

.. code-block:: console

    $ openstack image create ubuntu-mysql-5.7.1-dev \
      --public \
      --disk-format qcow2 \
      --container-format bare \
      --file ~/images/ubuntu_mysql.qcow2
    $ trove-manage datastore_version_update mysql 5.7.1 mysql $image_id "" 1
