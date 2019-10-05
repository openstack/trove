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

    git clone https://opendev.org/openstack/trove
    cd trove/integration/scripts

Build guest agent image
~~~~~~~~~~~~~~~~~~~~~~~

.. note::

    For testing purpose, the Trove guest images of some specific databases are
    periodically built and published in
    http://tarballs.openstack.org/trove/images/.

The trove guest agent image could be created by running the following command:

.. code-block:: console

    $ ./trovestack build-image \
        ${datastore_type} \
        ${guest_os} \
        ${guest_os_release} \
        ${dev_mode} \
        ${guest_username} \
        ${imagepath}

* Currently, only ``guest_os=ubuntu`` and ``guest_os_release=xenial`` are fully
  tested and supported.

* Default input values:

  .. code-block:: ini

      datastore_type=mysql
      guest_os=ubuntu
      guest_os_release=xenial
      dev_mode=true
      guest_username=ubuntu
      imagepath=$HOME/images/trove-${guest_os}-${guest_os_release}-${datastore_type}

* ``dev_mode=true`` is mainly for testing purpose for trove developers and it's
  necessary to build the image on the trove controller host, because the host
  and the guest VM need to ssh into each other without password. In this mode,
  when the trove guest agent code is changed, the image doesn't need to be
  rebuilt which is convenient for debugging. Trove guest agent will ssh into
  the host and download trove code during the service initialization.

* if ``dev_mode=false``, the trove code for guest agent is injected into the
  image at the building time. Now ``dev_mode=false`` is still in experimental
  and not considered production ready yet.

* Some other global variables:

  * ``HOST_SCP_USERNAME``: only used in dev mode, this is the user name used by
    guest agent to connect to the controller host, e.g. in devstack
    environment, it should be the ``stack`` user.
  * ``GUEST_WORKING_DIR``: The place to save the guest image, default value is
    ``$HOME/images``.
  * ``TROVE_BRANCH``: only used in dev mode. The branch name of Trove code
    repository, by default it's master, use other branches as needed such as
    stable/train.

For example, in order to build a MySQL image for Ubuntu Xenial operating
system in development mode:

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
      --file ~/images/ubuntu-mysql.qcow2
    $ trove-manage datastore_version_update mysql 5.7.1 mysql $image_id "" 1
