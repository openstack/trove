## Integration dev scripts, tests and docs for Trove.

***

### Steps to setup this environment:

Install a fresh Ubuntu 14.04 (Trusty Tahr) image ( _We suggest creating a development virtual machine using the image_ )

#### Login to the machine as root

#### Make sure we have git installed:

    # apt-get update
    # apt-get install git-core -y

#### Add a user named ubuntu if you do not already have one:

    # adduser ubuntu
    # visudo

  add this line to the file below the root user

    ubuntu  ALL=(ALL:ALL) ALL

    **OR use this if you dont want to type your password to sudo a command**

    ubuntu  ALL=(ALL) NOPASSWD: ALL

  if /dev/pts/0 does not have read/write for your user

    # chmod 666 /dev/pts/0

  *Note that this number can change and if you can not connect to the screen session then the /dev/pts/# needs modding like above.*

#### Login with ubuntu:

    # su ubuntu
    $ mkdir -p /opt/stack
    $ cd /opt/stack

#### Clone this repo:

    $ git clone https://github.com/openstack/trove.git

#### Go into the scripts directory:

    $ cd trove/integration/scripts/

#### Running trovestack is the core script:
*Run this to get the command list with a short description of each*

    $ ./trovestack

#### Install all the dependencies and then install trove via trovestack.
*This brings up trove (rd-api rd-tmgr) and initializes the trove database.*

    $ ./trovestack install

***

#### Connecting to the screen session

    $ screen -x stack

*If that command fails with the error*

    Cannot open your terminal '/dev/pts/1'

*If that command fails with the error chmod the corresponding /dev/pts/#*

    $ chmod 660 /dev/pts/1

#### Navigate the log screens
To produce the list of screens that you can scroll through and select

    ctrl+a then "

Num Name

..... (full list ommitted)

20 c-vol
21 h-eng
22 h-api
23 h-api-cfn
24 h-api-cw
25 tr-api
26 tr-tmgr
27 tr-cond

Alternatively, to go directly to a specific screen window

    ctrl+a then '

then enter a number (like 25) or name (like tr-api)

#### Detach from the screen session
Allows the services to continue running in the background

    ctrl+a then d

***

#### Kick start the build/test-init/build-image commands
*Add mysql as a parameter to set build and add the mysql guest image. This will also populate /etc/trove/test.conf with appropriate values for running the integration tests.*

    $ ./trovestack kick-start mysql

*Optional commands if you did not run kick-start*

#### Initialize the test configuration and set up test users (overwrites /etc/trove/test.conf)

    $ ./trovestack test-init

#### Build the image and add it to glance

    $ ./trovestack build-image mysql

***

### Reset your environment

#### Stop all the services running in the screens and refresh the environment:

    $ killall -9 screen
    $ screen -wipe
    $ RECLONE=yes ./trovestack install
    $ ./trovestack kick-start mysql

 or

    $ RECLONE=yes ./trovestack install
    $ ./trovestack test-init
    $ ./trovestack build-image mysql

***

### Recover after reboot
If the VM was restarted, then the process for bringing up Openstack and Trove is quite simple

    $./trovestack start-deps
    $./trovestack start

Use screen to ensure all modules have started without error

    $screen -r stack

***

### Running Integration Tests
Check the values in /etc/trove/test.conf in case it has been re-initialized prior to running the tests. For example, from the previous mysql steps:

    "dbaas_datastore": "%datastore_type%",
    "dbaas_datastore_version": "%datastore_version%",

should be:

    "dbaas_datastore": "mysql",
    "dbaas_datastore_version": "5.5",

Once Trove is running on DevStack, you can use the dev scripts to run the integration tests locally.

    $./trovestack int-tests

This will runs all of the blackbox tests by default. Use the --group option to run a different group:

    $./trovestack int-tests --group=simple_blackbox

You can also specify the TESTS_USE_INSTANCE_ID environment variable to have the integration tests use an existing instance for the tests rather than creating a new one.

    $./TESTS_DO_NOT_DELETE_INSTANCE=True TESTS_USE_INSTANCE_ID=INSTANCE_UUID ./trovestack int-tests --group=simple_blackbox

***

### VMware Fusion 5 speed improvement
Running Ubuntu with KVM or Qemu can be extremely slow without certain optimizations. The following are some VMware settings that can improve performance and may also apply to other virtualization platforms.

1. Shutdown the Ubuntu VM.

2. Go to VM Settings -> Processors & Memory -> Advanced Options.
   Check the "Enable hypervisor applications in this virtual machine"

3. Go to VM Settings -> Advanced.
   Set the "Troubleshooting" option to "None"

4. After setting these create a snapshot so that in cases where things break down you can revert to a clean snapshot.

5. Boot up the VM and run the `./trovestack install`

6. To verify that KVM is setup properly after the devstack installation you can run these commands.
```
ubuntu@ubuntu:~$ kvm-ok
INFO: /dev/kvm exists
KVM acceleration can be used
```

### VMware Workstation performance improvements

In recent versions of VMWare, you can get much better performance if you enable the right virtualization options. For example, in VMWare Workstation (found in version 10.0.2), click on VM->Settings->Processor.

You should see a box of "Virtualization Engine" options that can be changed only when the VM is shutdown.

Make sure you check "Virtualize Intel VT-x/EPT or AMD-V/RVI" and "Virtualize CPU performance counters". Set the preferred mode to "Automatic".

Then boot the VM and ensure that the proper virtualization is enabled.

```
ubuntu@ubuntu:~$ kvm-ok
INFO: /dev/kvm exists
KVM acceleration can be used
```
