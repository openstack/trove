# Steps
# 1 install nova via devstack
# 2 install reddwarf via this (or eventually mod devstack)
# 3 run tempest tests
cd ~
git clone git://github.com/openstack-dev/devstack.git
cd devstack
# Make sure every devstack instance on a new vm will get the default params for novaclient, paste, etc..
# We can change these to external flags in the future
echo "MYSQL_PASSWORD=e1a2c042c828d3566d0a
RABBIT_PASSWORD=f7999d1955c5014aa32c
SERVICE_TOKEN=be19c524ddc92109a224
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
keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 add-user-role $REDDWARF_USER $REDDWARF_ROLE $REDDWARF_TENANT

# Now attempt a login
curl -d '{"auth":{"passwordCredentials":{"username": "reddwarf", "password": "REDDWARF-PASS"},"tenantName":"reddwarf"}}' \
     -H "Content-type: application/json" http://localhost:35357/v2.0/tokens

#  now get a list of instances, which connects over python-novaclient to nova
# NOTE THIS AUTH TOKEN NEEDS TO BE CHANGED
# Also note that keystone uses the tenant id now and _not_ the name
#curl -H"content-type:application/xml" -H"X-Auth-Project-Id:$REDDWARF_TENANT" -H"X-Auth-User:reddwarf" \
#     -H'X-Auth-Key:2a2c89c6a7284d32bcb94b4e56f0411c' http://0.0.0.0:8779/v2/$REDDWARF_TENANT/instances

# Also, you should start up the api node like this
# bin/reddwarf-api-os-database --flagfile=etc/nova/nova.conf.template
