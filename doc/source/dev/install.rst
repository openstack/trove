.. _install:

==================
Trove Installation
==================

Trove is constantly under development. The easiest way to install
Trove is using the Trove integration scripts that can be found in
git in the `Trove Repository`_.


Steps to set up a Trove Developer Environment
=============================================

----------------
Installing trove
----------------

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
    # mkdir -p /opt/stack
    # cd /opt/stack

* Clone this repo::

    # git clone https://git.openstack.org/openstack/trove.git

* cd into the scripts directory::

    # cd trove/integration/scripts/

It is important to understand that this process is different now with
the elements and scripts being part of the trove repository. In the
past, one could clone trove-integration into the home directory and
run redstack from there, and it would clone trove in the right
place. And if you were making changes in trove-integration, it didn't
really matter where trove-integration was; it could be in home
directory or /opt/stack, or for that matter, anywhere. This is no
longer the case. If you are making changes to trove and would like to
run the trovestack script, you have to be sure that trove is in fact
cloned in /opt/stack as shown above.


---------------------------------
Running trovestack to setup Trove
---------------------------------

Now you run trovestack to help setup your development environment. For
complete details about the trovestack script refer to
trove/integration/README.md

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

References
==========

.. _Trove Repository: https://git.openstack.org/cgit/openstack/trove
