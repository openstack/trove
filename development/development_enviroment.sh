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
REDDWARF_TENANT=reddwarf
echo $REDDWARF_TENANT
echo $REDDWARF_USER
echo $REDDWARF_ROLE

# These all need to be set tenant did not work with the id but the name did match in the auth shim.
# REDDWARF_TOKEN=

# Now attempt a login
curl -d '{"auth":{"passwordCredentials":{"username": "reddwarf", "password": "REDDWARF-PASS"},"tenantName":"reddwarf"}}' \
     -H "Content-type: application/json" http://localhost:35357/v2.0/tokens | python -mjson.tool

#  now get a list of instances, which connects over python-novaclient to nova
# NOTE THIS AUTH TOKEN NEEDS TO BE CHANGED
# Also note that keystone uses the tenant id now and _not_ the name
# curl -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances
# curl -H"Content-type:application/json" -H"X-Auth-Token:$REDDWARF_TOKEN" \
#  http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances -d '{"name":"my_test","flavor":"1"}'


# sync up the database on first run!
# bin/reddwarf-manage --config-file=etc/reddwarf/reddwarf.conf.sample db_sync

# Also, you should start up the api node like this
# bin/reddwarf-server --config-file=etc/reddwarf/reddwarf.conf.sample


