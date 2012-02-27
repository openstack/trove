# At this point this script is manual. We will need to work this in to a more automated script.
# NOTE: Im not sure if we need any of this at this point. i will be checking/deleting it shortly.
# see bootstrap/bootstrap.sh

pkg_install () {
    echo Installing $@...
    sudo -E DEBIAN_FRONTEND=noninteractive $HTTP_PROXY apt-get -y --allow-unauthenticated --force-yes install $@
}

pkg_install debootstrap schroot apt-cacher-ng
# Make sure we sling up apt-cacher ng so each build is faster
echo 'Acquire::http { Proxy "http://127.0.0.1:3142"; };' | sudo tee /etc/apt/apt.conf.d/01proxy
sudo /etc/init.d/apt-cacher-ng restart

# This will wipe an existing schroot conf!
echo '
[oneiric]
description=Ubuntu oneiric
location=/var/chroot/oneiric
priority=3
users=<your user>
groups=sbuild
root-groups=root' | sudo tee /etc/schroot/schroot.conf

sudo rm -fr /var/chroot/oneiric
sudo debootstrap --variant=buildd oneiric /var/chroot/oneiric http://us.archive.ubuntu.com/ubuntu/

sudo mkdir /var/chroot/oneiric/root/.ssh
sudo cp ~/.ssh/id_rsa.pub /var/chroot/oneiric/root/.ssh/authorized_keys
sudo chroot /var/chroot/oneiric
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y --allow-unauthenticated --force-yes apt-get install openssh-server
DEBIAN_FRONTEND=noninteractive apt-get -y --allow-unauthenticated --force-yes install mysql-server
exit

#now that u are out of the vm, lets tar it up
cd /var/chroot/oneiric/
sudo tar czvf ../onieric_mysql.tar.gz .
cd ..
glance add -A $REDDWARF_TOKEN name="ubuntu-mysql.img" is_public=true type=raw < onieric_mysql.tar.gz

curl -H"Content-type:application/json" -H'X-Auth-Token:$REDDWARF_TOKEN' \
    http://0.0.0.0:8779/v0.1/$REDDWARF_TOKEN/instances \
    -d '{"name":"my_test","image":"$IMAGE_ID","flavor":"1"}'