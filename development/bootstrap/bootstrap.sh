EXPECTED_ARGS=1
if [ $# -ne $EXPECTED_ARGS ]
then
  echo "Usage: `basename $0` REDDWARF_TOKEN"
  exit 65
fi

# Be sure to pass in the token for glance auth
REDDWARF_TOKEN=$1
#
# This takes about ~12 minutes to finish
sudo apt-get -y install kvm-pxe ubuntu-vm-builder
VM_PATH=~/oneiric_mysql_image
UBUNTU_DISTRO="ubuntu 11.10"
UBUNTU_DISTRO_NAME=oneiric
USERNAME=reddwarf
rm -fr $VM_PATH

# Create the guest with the specific files
# Assuming this is run from development/bootstrap/bootstrap.sh
COPY_FILE=guest-agent-files.txt
rm -fr $COPY_FILE
# These will be the way the firstboot script phones home to get the latest guest via scp.
# See bootstrap_init.sh for more info on what it does
echo "$HOME/.ssh/id_rsa.pub /home/$USERNAME/.ssh/id_rsa.pub" >> $COPY_FILE
echo "$HOME/.ssh/id_rsa /home/$USERNAME/.ssh/id_rsa" >> $COPY_FILE

# Now put the pub key in this machines auth keys so the vm can log in to the host (scp)
# TODO(hub-cap): make this better using a ssh command or checking for existence
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys

#build a qemu image
sudo ubuntu-vm-builder qemu $UBUNTU_DISTRO_NAME --addpkg vim \
     --addpkg mysql-server --addpkg openssh-server \
     --copy $COPY_FILE --user $USERNAME --pass $USERNAME \
     --firstboot `pwd`/bootstrap_init.sh -d $VM_PATH

QCOW_IMAGE=`find $VM_PATH -name '*.qcow2'`

function get_id () {
    echo `$@ | awk '{print $6}'`
}

GLANCE_IMAGEID=`get_id glance add name="${UBUNTU_DISTRO_NAME}_mysql_image" is_public=true \
   container_format=ovf disk_format=qcow2 \
   distro='"$UBUNTU_DISTRO"' -A $REDDWARF_TOKEN < $QCOW_IMAGE`

echo "Run this query in your db"
echo "update service_images set image_id = '$GLANCE_IMAGEID';"