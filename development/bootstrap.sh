# At this point this script is manual. We will need to work this in to a more automated script.

pkg_install () {
    echo Installing $@...
    sudo -E DEBIAN_FRONTEND=noninteractive $HTTP_PROXY apt-get -y --allow-unauthenticated --force-yes install $@
}

pkg_install debootstrap schroot
echo '
[oneiric]
description=Ubuntu oneiric
location=/var/chroot/oneiric
priority=3
users=<your user>
groups=sbuild
root-groups=root' | sudo tee -a /etc/schroot/schroot.conf

sudo debootstrap --variant=buildd oneiric /var/chroot/oneiric http://us.archive.ubuntu.com/ubuntu/
sudo chroot /var/chroot/oneiric
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y --allow-unauthenticated --force-yes install mysql-server
exit

#now that u are out of the vm, lets tar it up
cd /var/chroot/oneiric/
sudo tar czvf ../onieric_mysql.tar.gz .

glance add -A $REDDWARF_TOKEN name="ubuntu-mysql.img" is_public=true type=raw < onieric_mysql.tar.gz
