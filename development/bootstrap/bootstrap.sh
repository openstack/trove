# Be sure to pass in the token for glance auth
REDDWARF_TOKEN=$1
# This takes about ~12 minutes to finish
sudo apt-get install kvm-pxe
VM_PATH=oneiric_mysql_image
UBUNTU_DISTRO="ubuntu 11.10"
UBUNTU_DISTRO_NAME=oneiric
rm -fr $VM_PATH

#build a qemu image
sudo ubuntu-vm-builder qemu $UBUNTU_DISTRO_NAME --addpkg vim \
     --addpkg mysql-server --addpkg openssh-server --addpkg kvm-pxe \
     --user reddwarf --pass reddwarf -d $VM_PATH

QCOW_IMAGE=`find $VM_PATH -name '*.qcow2'`
glance add name="lucid_mysql_image" is_public=true \
   container_format=ovf disk_format=qcow2 \
   distro="$UBUNTU_DISTRO" -A $REDDWARF_TOKEN < $QCOW_IMAGE
