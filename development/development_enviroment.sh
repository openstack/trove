# Steps
# 1 install nova via devstack
# 2 install reddwarf via this (or eventually mod devstack)
# 3 run tempest tests

#Kind of annoying, but the lxml stuff does not work unless u have these installed
sudo apt-get install libxml2-dev libxslt-dev

cd ~
git clone git://github.com/openstack-dev/devstack.git
cd devstack
# Make sure every devstack instance on a new vm will get the default params for novaclient, paste, etc..
# We can change these to external flags in the future
echo "MYSQL_PASSWORD=e1a2c042c828d3566d0a
RABBIT_PASSWORD=f7999d1955c5014aa32c
SERVICE_TOKEN=be19c524ddc92109a224
SERVICE_PASSWORD=3de4922d8b6ac5a1aad9
ADMIN_PASSWORD=3de4922d8b6ac5a1aad9" > localrc

./stack.sh

# Now add a user to keystone that is reddwarf specific. This is what we will use in dev/test to authenticate against keystone
# the get_id is stolen from devstack :D
function get_id () {
    echo `$@ | grep id | awk '{print $4}'`
}
# NOTE THIS AUTH TOKEN NEEDS TO BE CHANGED
REDDWARF_TENANT=`get_id keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 tenant-create --name=reddwarf`
REDDWARF_USER=`get_id keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 user-create \
                                                        --name=reddwarf --pass="REDDWARF-PASS" --email=reddwarf@example.com`
REDDWARF_ROLE=`get_id keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 role-create --name=reddwarf`
keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 user-role-add --tenant_id $REDDWARF_TENANT \
                                 --user $REDDWARF_USER \
                                 --role $REDDWARF_ROLE
# These are the values
#REDDWARF_TENANT=reddwarf
REDDWARF_TENANT=`keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 tenant-list| grep reddwarf | cut -d ' ' -f 2`
echo $REDDWARF_TENANT
REDDWARF_USER=`keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 user-list| grep reddwarf | cut -d ' ' -f 2`
echo $REDDWARF_USER
REDDWARF_TOKEN=$(curl -d '{"auth":{"passwordCredentials":{"username": "reddwarf", "password": "REDDWARF-PASS"},"tenantName":"reddwarf"}}' -H "Content-type: application/json" http://localhost:35357/v2.0/tokens | python -mjson.tool | grep id | tr -s ' ' | cut -d ' ' -f 3 | sed s/\"/''/g | awk 'NR==2' | cut -d ',' -f 1)
echo $REDDWARF_TOKEN


# Now attempt a login
#curl -d '{"auth":{"passwordCredentials":{"username": "reddwarf", "password": "REDDWARF-PASS"},"tenantName":"reddwarf"}}' \
#     -H "Content-type: application/json" http://localhost:35357/v2.0/tokens | python -mjson.tool

#  now get a list of instances, which connects over python-novaclient to nova
# NOTE THIS AUTH TOKEN NEEDS TO BE CHANGED
# Also note that keystone uses the tenant id now and _not_ the name
# list instances
# curl -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances | python -mjson.tool
# old create instance:
# curl -H"Content-type:application/json" -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances -d '{"name":"my_test","flavor":"1"}'  | python -mjson.tool
# create instance:
# curl -H"Content-type:application/json" -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances -d '{"instance": {"databases": [{"character_set": "utf8", "collate": "utf8_general_ci", "name": "sampledb"}, {"name": "nextround"}], "flavorRef": "http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/flavors/1", "name": "json_rack_instance", "volume": {"size": "2"}}}'| python -mjson.tool
# {
#     "instance": {
#         "databases": [
#             {
#                 "character_set": "utf8",
#                 "collate": "utf8_general_ci",
#                 "name": "sampledb"
#             },
#             {
#                 "name": "nextround"
#             }
#         ],
#         "flavorRef": "http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/flavors/1",
#         "name": "json_rack_instance",
#         "volume": {
#             "size": "2"
#         }
#     }
# }

# DELETE INSTANCE
# curl -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances/id -X DELETE | python -mjson.tool


# update the etc/reddwarf/reddwarf.conf.sample
# add this config setting
# reddwarf_tenant_id = f5f71240a97c411e977452370422d7cc

# sync up the database on first run!
# bin/reddwarf-manage --config-file=etc/reddwarf/reddwarf.conf.sample db_sync

# Also, you should start up the api node like this
# bin/reddwarf-server --config-file=etc/reddwarf/reddwarf.conf.sample

# need to build the image before we can create a new instance
# need an rsa key to build the

# ssh-keygen

# first time build the image for reddwarf
# ./bootstrap/bootstrap.sh

##### re-add image manually #####
VM_PATH=~/oneiric_mysql_image
UBUNTU_DISTRO="ubuntu 11.10"
UBUNTU_DISTRO_NAME=oneiric
QCOW_IMAGE=`find $VM_PATH -name '*.qcow2'`
function get_glance_id () {
    echo `$@ | awk '{print $6}'`
}
glance add name="oneiric_mysql_image" is_public=true container_format=ovf disk_format=qcow2 distro='"ubuntu 11.10"' -A $REDDWARF_TOKEN < $QCOW_IMAGE
# GLANCE_IMAGEID=
echo "updating your database - $GLANCE_IMAGEID"
sqlite3 /src/reddwarf_test.sqlite "INSERT INTO service_images VALUES('1', 'database', '$GLANCE_IMAGEID');"
#sqlite3 /src/reddwarf_test.sqlite "UPDATE service_images set image_id='$GLANCE_IMAGEID';"
echo "done GLANCE IMAGE ID = $GLANCE_IMAGEID"

# add the image to the reddwarf database
# get the image id from glance
# glance index -A $REDDWARF_TOKEN
# REDDWARF_IMAGE_ID=a92615d7-a8ba-45ff-b29f-ec2baf6b8348
# (sqlite)
# sqlite3 reddwarf_test.sqlite "insert into service_images values ('$REDDWARF_IMAGE_ID','database', '$REDDWARF_IMAGE_ID');"

