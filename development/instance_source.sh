#!/bin/bash

function reddwarf_auth {
    REDDWARF_TENANT=`keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 tenant-list| grep reddwarf | cut -d ' ' -f 2`
    REDDWARF_USER=`keystone --endpoint http://localhost:35357/v2.0 --token be19c524ddc92109a224 user-list| grep reddwarf | cut -d ' ' -f 2`
    REDDWARF_TOKEN=$(curl -d '{"auth":{"passwordCredentials":{"username": "reddwarf", "password": "REDDWARF-PASS"},"tenantName":"reddwarf"}}' -H "Content-type: application/json" http://localhost:35357/v2.0/tokens | python -mjson.tool | grep id | tr -s ' ' | cut -d ' ' -f 3 | sed s/\"/''/g | awk 'NR==2' | cut -d ',' -f 1)
    export REDDWARF_TENANT
    export REDDWARF_USER
    export REDDWARF_TOKEN
    echo "REDDWARF_TENANT = $REDDWARF_TENANT"
    echo "REDDWARF_USER = $REDDWARF_USER"
    echo "REDDWARF_TOKEN = $REDDWARF_TOKEN"
}

function create_instance {
    FLAVOR_ID=$1
    curl -H"Content-type:application/json" -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances -d '{"instance": {"databases": [{"character_set": "utf8", "collate": "utf8_general_ci", "name": "sampledb"}, {"name": "nextround"}], "flavorRef": "http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/flavors/1", "name": "json_rack_instance"}}' | python -mjson.tool
}

function list_instances {
    curl -H"X-Auth-Token:$REDDWARF_TOKEN" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances | python -mjson.tool
}

function delete_instance {
    INSTANCE_ID=$1
    curl -H"X-Auth-Token:$REDDWARF_TOKEN" -H"ACCEPT:application/json" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances/$INSTANCE_ID -X DELETE | python -mjson.tool
}

function show_instance {
    INSTANCE_ID=$1
    curl -H"X-Auth-Token:$REDDWARF_TOKEN" -H"ACCEPT:application/json" http://0.0.0.0:8779/v0.1/$REDDWARF_TENANT/instances/$INSTANCE_ID | python -mjson.tool
}

