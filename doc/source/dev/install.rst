.. _install:

==================
Trove Installation
==================

Trove is constantly under development. The easiest way to install
Trove is using the Trove integration scripts that can be found in
git in the `Trove Integration Repository`_.


Steps to set up a Trove Developer Environment
=============================================

----------------------------
Installing trove-integration
----------------------------

* Install a fresh Ubuntu 14.04 (Trusty Tahr) image (preferably a
  virtual machine)

* Make sure we have git installed::

    # apt-get update
    # apt-get install git -y

* Add a user named ubuntu if you do not already have one::

    # adduser ubuntu

* Set the ubuntu user up with sudo access::

    # visudo

  Add *ubuntu  ALL=(ALL) NOPASSWD: ALL* to the sudoers file.

* Login with ubuntu::

    # su ubuntu
    # cd ~

* Clone this repo::

    # git clone https://git.openstack.org/openstack/trove-integration.git

* cd into the scripts directory::

    # cd trove-integration/scripts/


---------------------------------
Running redstack to install Trove
---------------------------------

Redstack is the core script that allows you to install and interact
with your developer installation of Trove. Redstack has the following
options that you can run.

* Get the command list with a short description of each command and
  what it does::

    # ./redstack

* Install all the dependencies and then install Trove. This brings up
  trove (tr-api tr-tmgr tr-cond) and initializes the trove database::

    # ./redstack install

* Kick start the build/test-init/build-image commands. Add mysql as a
  parameter to set build and add the mysql guest image::

    # ./redstack kick-start mysql

* You may need to add this iptables rule, so be sure to save it!::

    # sudo iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o eth0 -j
    MASQUERADE


------------------------
Running the trove client
------------------------

* The trove client is run using the trove command. You can show the
  complete documentation on the shell by running trove help::

    # trove help


-----------------------
Running the nova client
-----------------------

* The nova client is run using the nova command. You can show the
  complete documentation on the shell by running nova help:::

    # nova help


More information
================

For more information and help on how to use redstack and other
trove-integration scripts, please look at the `README documentation`_
in the `Trove Integration Repository`_.


.. _Trove Integration Repository: https://git.openstack.org/cgit/openstack/trove-integration
.. _README documentation: https://git.openstack.org/cgit/openstack/trove-integration/plain/README.md
