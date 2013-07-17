.. _install:

==================
Trove Installation
==================

Trove is constantly under development. The easiest way to install
Trove is using the Trove integration scripts that can be found in
github in the `Trove Integration Repository`_.


Steps to set up a Trove Developer Environment
=============================================

----------------------------
Installing trove-integration
----------------------------

* Install a fresh Ubuntu 12.04 (Precise Pangolin) image (preferably a
  virtual machine)

* Make sure we have git installed::

    # apt-get update
    # apt-get install git-core -y

* Add a user named ubuntu if you do not already have one::

    # adduser ubuntu

* Set the ubuntu user up with sudo access::

    # visudo

  Add *ubuntu  ALL=(ALL) NOPASSWD: ALL* to the sudoers file.

* Login with ubuntu::

    # su ubuntu
    # cd ~

* Clone this repo::

    # git clone https://github.com/openstack/trove-integration.git

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
  trove (rd-api rd-tmgr) and initializes the trove database::

    # ./redstack install

* Kick start the build/test-init/build-image commands. Add mysql as a
  parameter to set build and add the mysql guest image::

    # ./redstack kick-start mysql

* You probably need to add this iptables rule, so be sure to save it!::

    # sudo iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o eth0 -j
    MASQUERADE


------------------------
Running the trove client
------------------------

* rd-client sets of the authorization endpoint and gets a token for you::

    # ./redstack rd-client


-----------------------
Running the nova client
-----------------------

* nova-client sets of the authorization endpoint and gets a token for you::

    # ./redstack nova-client


More information
================

For more information and help on how to use redstack and other
trove-integration scripts, please look at the `README documentation`_
in the `Trove Integration Repository`_.


.. _Trove Integration Repository: https://www.github.com/openstack/trove-integration
.. _README documentation: https://github.com/openstack/trove-integration/blob/master/README.md
