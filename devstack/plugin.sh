#!/bin/bash
#
# lib/trove
# Functions to control the configuration and operation of the **Trove** service

# Dependencies:
# ``functions`` file
# ``DEST``, ``STACK_USER`` must be defined
# ``SERVICE_{HOST|PROTOCOL|TOKEN}`` must be defined

# ``stack.sh`` calls the entry points in this order:
#
# install_trove
# install_python_troveclient
# configure_trove
# init_trove
# start_trove
# stop_trove
# cleanup_trove

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set +o xtrace

# Functions
# ---------

# Test if any Trove services are enabled
# is_trove_enabled
function is_trove_enabled {
    [[ ,${ENABLED_SERVICES} =~ ,"tr-" ]] && return 0
    return 1
}

# setup_trove_logging() - Adds logging configuration to conf files
function setup_trove_logging {
    local CONF=$1
    iniset $CONF DEFAULT debug $ENABLE_DEBUG_LOG_LEVEL
    iniset $CONF DEFAULT use_syslog $SYSLOG
    if [ "$LOG_COLOR" == "True" ] && [ "$SYSLOG" == "False" ]; then
        # Add color to logging output
        setup_colorized_logging $CONF DEFAULT tenant user
    fi
}

# create_trove_accounts() - Set up common required trove accounts

# Tenant               User       Roles
# ------------------------------------------------------------------
# service              trove     admin        # if enabled

function create_trove_accounts {
    if [[ "$ENABLED_SERVICES" =~ "trove" ]]; then
        create_service_user "trove" "admin"

        # Add trove user to the clouds.yaml
        CLOUDS_YAML=${CLOUDS_YAML:-/etc/openstack/clouds.yaml}
        $PYTHON $TOP_DIR/tools/update_clouds_yaml.py \
            --file $CLOUDS_YAML \
            --os-cloud trove \
            --os-region-name $REGION_NAME \
            $CA_CERT_ARG \
            --os-auth-url $KEYSTONE_SERVICE_URI \
            --os-username trove \
            --os-password $SERVICE_PASSWORD \
            --os-project-name $SERVICE_PROJECT_NAME

        local trove_service=$(get_or_create_service "trove" \
            "database" "Trove Service")
        get_or_create_endpoint $trove_service \
            "$REGION_NAME" \
            "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s" \
            "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s" \
            "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s"
    fi
}

# Removes all the WSGI related files and restart apache.
function cleanup_trove_apache_wsgi {
    sudo rm -rf $TROVE_WSGI_DIR
    sudo rm -f $(apache_site_config_for trove-api)
    restart_apache_server
}

# stack.sh entry points
# ---------------------

# cleanup_trove() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_trove {
    # Clean up dirs
    rm -fr $TROVE_CONF_DIR/*

    if is_service_enabled horizon; then
        cleanup_trove_dashboard
    fi

    if [[ "${TROVE_USE_MOD_WSGI}" == "TRUE" ]]; then
        echo "Cleaning up Trove's WSGI setup"
        cleanup_trove_apache_wsgi
    fi
}


# cleanup_trove_dashboard() - Remove Trove dashboard files from Horizon
function cleanup_trove_dashboard {
    rm -f $HORIZON_DIR/openstack_dashboard/local/enabled/_17*database*.py
}


# iniset_conditional() - Sets the value in the inifile, but only if it's
# actually got a value
function iniset_conditional {
    local FILE=$1
    local SECTION=$2
    local OPTION=$3
    local VALUE=$4

    if [[ -n "$VALUE" ]]; then
        iniset ${FILE} ${SECTION} ${OPTION} ${VALUE}
    fi
}

# configure_keystone_token_life() - update the keystone token life to 3h
function configure_keystone_token_life() {
    KEYSTONE_CONF_DIR=${KEYSTONE_CONF_DIR:-/etc/nova}
    KEYSTONE_CONF=${KEYSTONE_CONF:-${KEYSTONE_CONF_DIR}/keystone.conf}
    KEYSTONE_TOKEN_LIFE=${KEYSTONE_TOKEN_LIFE:-10800}
    iniset $KEYSTONE_CONF token expiration ${KEYSTONE_TOKEN_LIFE}
    echo "configure_keystone_token_life: setting keystone token life to ${KEYSTONE_TOKEN_LIFE}"
    echo "configure_keystone_token_life: restarting Keystone"
    stop_keystone
    start_keystone
}

# configure_nova_kvm() - update the nova hypervisor configuration if possible
function configure_nova_kvm {
    cpu="unknown"

    if [ -e /sys/module/kvm_*/parameters/nested ]; then
        reconfigure_nova="F"

        if [ -e /sys/module/kvm_intel/parameters/nested ]; then
            cpu="Intel"
            if [[ "$(cat /sys/module/kvm_*/parameters/nested)" == "Y" ]]; then
                reconfigure_nova="Y"
            fi
        elif [ -e /sys/module/kvm_amd/parameters/nested ]; then
            cpu="AMD"
            if [[ "$(cat /sys/module/kvm_*/parameters/nested)" == "1" ]]; then
                reconfigure_nova="Y"
            fi
        fi

        if [ "${reconfigure_nova}" == "Y" ]; then
            NOVA_CONF_DIR=${NOVA_CONF_DIR:-/etc/nova}
            NOVA_CONF=${NOVA_CONF:-${NOVA_CONF_DIR}/nova.conf}
            iniset $NOVA_CONF libvirt cpu_mode "none"
            iniset $NOVA_CONF libvirt virt_type "kvm"
        fi
    fi

    virt_type=$(iniget $NOVA_CONF libvirt virt_type)
    echo "configure_nova_kvm: using virt_type: ${virt_type} for cpu: ${cpu}."
}

# Setup WSGI config files for Trove and enable the site
function config_trove_apache_wsgi {
    local trove_apache_conf

    sudo mkdir -p ${TROVE_WSGI_DIR}
    sudo cp $TROVE_DIR/trove/cmd/app.wsgi $TROVE_WSGI_DIR/app.wsgi
    trove_apache_conf=$(apache_site_config_for trove-api)
    sudo cp $TROVE_DEVSTACK_FILES/apache-trove-api.template ${trove_apache_conf}
    sudo sed -e "
        s|%TROVE_SERVICE_PORT%|${TROVE_SERVICE_PORT}|g;
        s|%TROVE_WSGI_DIR%|${TROVE_WSGI_DIR}|g;
        s|%USER%|${STACK_USER}|g;
        s|%APACHE_NAME%|${APACHE_NAME}|g;
        s|%APIWORKERS%|${API_WORKERS}|g;
    " -i ${trove_apache_conf}
    enable_apache_site trove-api
}

# configure_trove() - Set config files, create data dirs, etc
function configure_trove {
    setup_develop $TROVE_DIR

    # Temporarily disable re-configuring nova_kvm until
    # more nodes in the pool can support it without crashing.
    # configure_nova_kvm
    configure_keystone_token_life

    # Create the trove conf dir and cache dirs if they don't exist
    sudo install -d -o $STACK_USER ${TROVE_CONF_DIR}
    # Copy api-paste file over to the trove conf dir
    cp $TROVE_LOCAL_API_PASTE_INI $TROVE_API_PASTE_INI
    # configure apache related files
    if [[ "${TROVE_USE_MOD_WSGI}" == "TRUE" ]]; then
        echo "Configuring Trove to use mod-wsgi and Apache"
        config_trove_apache_wsgi
    fi
    # (Re)create trove conf files
    rm -f $TROVE_CONF $TROVE_GUESTAGENT_CONF

    TROVE_AUTH_ENDPOINT=$KEYSTONE_AUTH_URI/v$IDENTITY_API_VERSION

    ################################################################ trove conf
    setup_trove_logging $TROVE_CONF
    iniset_conditional $TROVE_CONF DEFAULT max_accepted_volume_size $TROVE_MAX_ACCEPTED_VOLUME_SIZE
    iniset_conditional $TROVE_CONF DEFAULT max_instances_per_tenant $TROVE_MAX_INSTANCES_PER_TENANT
    iniset_conditional $TROVE_CONF DEFAULT max_volumes_per_tenant $TROVE_MAX_VOLUMES_PER_TENANT
    iniset_conditional $TROVE_CONF DEFAULT agent_call_low_timeout $TROVE_AGENT_CALL_LOW_TIMEOUT
    iniset_conditional $TROVE_CONF DEFAULT agent_call_high_timeout $TROVE_AGENT_CALL_HIGH_TIMEOUT
    iniset_conditional $TROVE_CONF DEFAULT resize_time_out $TROVE_RESIZE_TIME_OUT
    iniset_conditional $TROVE_CONF DEFAULT usage_timeout $TROVE_USAGE_TIMEOUT
    iniset_conditional $TROVE_CONF DEFAULT state_change_wait_time $TROVE_STATE_CHANGE_WAIT_TIME
    iniset_conditional $TROVE_CONF DEFAULT reboot_time_out 300
    iniset $TROVE_CONF DEFAULT controller_address ${SERVICE_HOST}

    configure_keystone_authtoken_middleware $TROVE_CONF trove
    iniset $TROVE_CONF service_credentials username trove
    iniset $TROVE_CONF service_credentials user_domain_name Default
    iniset $TROVE_CONF service_credentials project_domain_name Default
    iniset $TROVE_CONF service_credentials password $SERVICE_PASSWORD
    iniset $TROVE_CONF service_credentials project_name $SERVICE_PROJECT_NAME
    iniset $TROVE_CONF service_credentials region_name $REGION_NAME
    iniset $TROVE_CONF service_credentials auth_url $TROVE_AUTH_ENDPOINT

    iniset $TROVE_CONF database connection `database_connection_url trove`

    iniset $TROVE_CONF DEFAULT rpc_backend "rabbit"
    iniset $TROVE_CONF DEFAULT control_exchange trove
    iniset $TROVE_CONF DEFAULT transport_url rabbit://$RABBIT_USERID:$RABBIT_PASSWORD@$RABBIT_HOST:5672/
    iniset $TROVE_CONF DEFAULT trove_api_workers "$API_WORKERS"
    iniset $TROVE_CONF DEFAULT taskmanager_manager trove.taskmanager.manager.Manager
    iniset $TROVE_CONF DEFAULT default_datastore $TROVE_DATASTORE_TYPE

    iniset $TROVE_CONF cassandra tcp_ports 7000,7001,7199,9042,9160
    iniset $TROVE_CONF couchbase tcp_ports 8091,8092,4369,11209-11211,21100-21199
    iniset $TROVE_CONF couchdb tcp_ports 5984
    iniset $TROVE_CONF db2 tcp_ports 50000
    iniset $TROVE_CONF mariadb tcp_ports 3306,4444,4567,4568
    iniset $TROVE_CONF mongodb tcp_ports 2500,27017,27019
    iniset $TROVE_CONF mysql tcp_ports 3306
    iniset $TROVE_CONF percona tcp_ports 3306
    iniset $TROVE_CONF postgresql tcp_ports 5432
    iniset $TROVE_CONF pxc tcp_ports 3306,4444,4567,4568
    iniset $TROVE_CONF redis tcp_ports 6379,16379
    iniset $TROVE_CONF vertica tcp_ports 5433,5434,5444,5450,4803

    ################################################################ trove guest agent conf
    setup_trove_logging $TROVE_GUESTAGENT_CONF

    iniset_conditional $TROVE_GUESTAGENT_CONF DEFAULT state_change_wait_time $TROVE_STATE_CHANGE_WAIT_TIME
    iniset_conditional $TROVE_GUESTAGENT_CONF DEFAULT command_process_timeout $TROVE_COMMAND_PROCESS_TIMEOUT
    iniset $TROVE_GUESTAGENT_CONF DEFAULT rpc_backend "rabbit"
    iniset $TROVE_GUESTAGENT_CONF DEFAULT transport_url rabbit://$RABBIT_USERID:$RABBIT_PASSWORD@$TROVE_HOST_GATEWAY:5672/
    iniset $TROVE_GUESTAGENT_CONF DEFAULT control_exchange trove
    iniset $TROVE_GUESTAGENT_CONF DEFAULT ignore_users os_admin
    iniset $TROVE_GUESTAGENT_CONF DEFAULT log_dir /var/log/trove/
    iniset $TROVE_GUESTAGENT_CONF DEFAULT log_file trove-guestagent.log

    iniset $TROVE_GUESTAGENT_CONF service_credentials username trove
    iniset $TROVE_GUESTAGENT_CONF service_credentials user_domain_name Default
    iniset $TROVE_GUESTAGENT_CONF service_credentials project_domain_name Default
    iniset $TROVE_GUESTAGENT_CONF service_credentials password $SERVICE_PASSWORD
    iniset $TROVE_GUESTAGENT_CONF service_credentials project_name $SERVICE_PROJECT_NAME
    iniset $TROVE_GUESTAGENT_CONF service_credentials region_name $REGION_NAME
    iniset $TROVE_GUESTAGENT_CONF service_credentials auth_url $TROVE_AUTH_ENDPOINT

    # 1. To avoid 'Connection timed out' error of sudo command inside the guest agent
    # 2. Config the controller IP address used by guest-agent to download Trove code during initialization (only valid for dev_mode=true).
    common_cloudinit=/etc/trove/cloudinit/common.cloudinit
    sudo mkdir -p $(dirname ${common_cloudinit})
    sudo touch ${common_cloudinit}
    sudo tee ${common_cloudinit} >/dev/null <<EOF
#cloud-config
manage_etc_hosts: "localhost"
write_files:
  - path: /etc/trove/controller.conf
    content: |
      CONTROLLER=${SERVICE_HOST}
EOF

    # NOTE(lxkong): Remove this when we support common cloud-init file for all datastores.
    for datastore in "mysql" "mariadb" "postgresql"
    do
        sudo cp ${common_cloudinit} /etc/trove/cloudinit/${datastore}.cloudinit
    done
}

# install_trove() - Collect source and prepare
function install_trove {
    install_package jq

    echo "Changing stack user sudoers"
    echo "stack ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/60_stack_sh_allow_all

    setup_develop $TROVE_DIR

    if [[ "${TROVE_USE_MOD_WSGI}" == "TRUE" ]]; then
        echo "Installing apache wsgi"
        install_apache_wsgi
    fi

    if is_service_enabled horizon; then
        install_trove_dashboard
    fi

    # Fix iptables rules that prevent amqp connections from the devstack box to the guests
    sudo iptables -D openstack-INPUT -j REJECT --reject-with icmp-host-prohibited || true
}

# install_trove_dashboard() - Collect source and prepare
function install_trove_dashboard {
    git_clone $TROVE_DASHBOARD_REPO $TROVE_DASHBOARD_DIR $TROVE_DASHBOARD_BRANCH
    setup_develop $TROVE_DASHBOARD_DIR
    cp $TROVE_DASHBOARD_DIR/trove_dashboard/enabled/_17*database*.py $HORIZON_DIR/openstack_dashboard/local/enabled
}

# install_python_troveclient() - Collect source and prepare
function install_python_troveclient {
    if use_library_from_git "python-troveclient"; then
        git_clone $TROVE_CLIENT_REPO $TROVE_CLIENT_DIR $TROVE_CLIENT_BRANCH
        setup_develop $TROVE_CLIENT_DIR
    fi
}

function init_trove_db {
    # (Re)Create trove db
    recreate_database trove

    # Initialize the trove database
    $TROVE_MANAGE db_sync
}

function create_mgmt_subnet_v4 {
    local project_id=$1
    local net_id=$2
    local name=$3
    local ip_range=$4

    subnet_id=$(openstack subnet create --project ${project_id} --ip-version 4 --subnet-range ${ip_range} --gateway none --dns-nameserver 8.8.8.8 --network ${net_id} $name -c id -f value)
    die_if_not_set $LINENO subnet_id "Failed to create private IPv4 subnet for network: ${net_id}, project: ${project_id}"
    echo $subnet_id
}

# Create private IPv6 subnet
# Note: Trove is not fully tested in IPv6.
function create_subnet_v6 {
    local project_id=$1
    local net_id=$2
    local name=$3
    local subnet_params="--ip-version 6 "

    die_if_not_set $LINENO IPV6_RA_MODE "IPV6 RA Mode not set"
    die_if_not_set $LINENO IPV6_ADDRESS_MODE "IPV6 Address Mode not set"
    local ipv6_modes="--ipv6-ra-mode $IPV6_RA_MODE --ipv6-address-mode $IPV6_ADDRESS_MODE"

    if [[ -n "$IPV6_PRIVATE_NETWORK_GATEWAY" ]]; then
        subnet_params+="--gateway $IPV6_PRIVATE_NETWORK_GATEWAY "
    fi
    if [[ -n $SUBNETPOOL_V6_ID ]]; then
        subnet_params+="--subnet-pool $SUBNETPOOL_V6_ID "
    else
        subnet_params+="--subnet-range $FIXED_RANGE_V6 $ipv6_modes} "
    fi
    subnet_params+="--network $net_id $name "

    ipv6_subnet_id=$(openstack --project ${project_id} subnet create $subnet_params | grep ' id ' | get_field 2)
    die_if_not_set $LINENO ipv6_subnet_id "Failed to create private IPv6 subnet for network: ${net_id}, project: ${project_id}"
    echo $ipv6_subnet_id
}

function setup_mgmt_network() {
    local PROJECT_ID=$1
    local NET_NAME=$2
    local SUBNET_NAME=$3
    local SUBNET_RANGE=$4
    local SHARED=$5

    local share_flag=""
    if [[ "${SHARED}" == "TRUE" ]]; then
        share_flag="--share"
    fi

    network_id=$(openstack network create --project ${PROJECT_ID} ${share_flag} $NET_NAME -c id -f value)
    die_if_not_set $LINENO network_id "Failed to create network: $NET_NAME, project: ${PROJECT_ID}"

    if [[ "$IP_VERSION" =~ 4.* ]]; then
        net_subnet_id=$(create_mgmt_subnet_v4 ${PROJECT_ID} ${network_id} ${SUBNET_NAME} ${SUBNET_RANGE})
        # 'openstack router add' has a bug that cound't show the error message
        # openstack router add subnet ${ROUTER_ID} ${net_subnet_id} --debug
    fi

    # Trove doesn't support IPv6 for now.
#    if [[ "$IP_VERSION" =~ .*6 ]]; then
#        NEW_IPV6_SUBNET_ID=$(create_subnet_v6 ${PROJECT_ID} ${network_id} ${IPV6_SUBNET_NAME})
#        openstack router add subnet $ROUTER_ID $NEW_IPV6_SUBNET_ID
#    fi
}

# start_trove() - Start running processes, including screen
function start_trove {
    if [[ ${TROVE_USE_MOD_WSGI}" == TRUE" ]]; then
        echo "Restarting Apache server ..."
        enable_apache_site trove-api
        restart_apache_server
    else
        run_process tr-api "$TROVE_BIN_DIR/trove-api --config-file=$TROVE_CONF"
    fi
    run_process tr-tmgr "$TROVE_BIN_DIR/trove-taskmanager --config-file=$TROVE_CONF"
    run_process tr-cond "$TROVE_BIN_DIR/trove-conductor --config-file=$TROVE_CONF"
}

# stop_trove() - Stop running processes
function stop_trove {
    # Kill the trove screen windows
    local serv
    if [[ ${TROVE_USE_MOD_WSGI} == "TRUE" ]]; then
        echo "Disabling Trove API in Apache"
        disable_apache_site trove-api
    else
        stop_process tr-api
    fi
    for serv in tr-tmgr tr-cond; do
        stop_process $serv
    done
}

# configure_tempest_for_trove() - Set Trove related setting on Tempest
# NOTE (gmann): Configure all the Tempest setting for Trove service in
# this function.
function configure_tempest_for_trove {
    if is_service_enabled tempest; then
        iniset $TEMPEST_CONFIG service_available trove True
    fi
}

# Use trovestack to create guest image and register the image in the datastore.
function create_guest_image {
    TROVE_ENABLE_IMAGE_BUILD=`echo ${TROVE_ENABLE_IMAGE_BUILD,,}`
    if [[ ${TROVE_ENABLE_IMAGE_BUILD} == "false" ]]; then
        echo "Skip creating guest image."
        return 0
    fi

    image_name="trove-guest-${TROVE_IMAGE_OS}-${TROVE_IMAGE_OS_RELEASE}"
    mkdir -p $HOME/images
    image_file=$HOME/images/${image_name}.qcow2

    if [[ -n ${TROVE_NON_DEV_IMAGE_URL} ]]; then
        echo "Downloading guest image from ${TROVE_NON_DEV_IMAGE_URL}"
        curl -sSL ${TROVE_NON_DEV_IMAGE_URL} -o ${image_file}
    else
        echo "Starting to create guest image"

        $DEST/trove/integration/scripts/trovestack \
          build-image \
          ${TROVE_IMAGE_OS} \
          ${TROVE_IMAGE_OS_RELEASE} \
          true \
          ${TROVE_IMAGE_OS} \
          ${image_file}
    fi

    if [[ ! -f ${image_file} ]]; then
        echo "Image file was not found at ${image_file}"
        exit 1
    fi

    echo "Add the image to glance"
    glance_image_id=$(openstack --os-region-name RegionOne --os-password ${SERVICE_PASSWORD} \
      --os-project-name service --os-username trove \
      image create ${image_name} \
      --disk-format qcow2 --container-format bare \
      --tag trove \
      --property hw_rng_model='virtio' \
      --file ${image_file} \
      --debug \
      -c id -f value)
     echo "Glance image ${glance_image_id} uploaded"

    echo "Register the image in datastore"
    $TROVE_MANAGE datastore_update $TROVE_DATASTORE_TYPE ""
    $TROVE_MANAGE datastore_version_update $TROVE_DATASTORE_TYPE $TROVE_DATASTORE_VERSION $TROVE_DATASTORE_TYPE "" "" 1 --image-tags trove
    $TROVE_MANAGE datastore_update $TROVE_DATASTORE_TYPE $TROVE_DATASTORE_VERSION

    echo "Add parameter validation rules if available"
    if [[ -f $DEST/trove/trove/templates/$TROVE_DATASTORE_TYPE/validation-rules.json ]]; then
        $TROVE_MANAGE db_load_datastore_config_parameters "$TROVE_DATASTORE_TYPE" "$TROVE_DATASTORE_VERSION" \
            $DEST/trove/trove/templates/$TROVE_DATASTORE_TYPE/validation-rules.json
    fi
}

# Set up Trove management network and make configuration change.
function config_trove_network {
    echo "Finalizing Neutron networking for Trove"
    echo "Dumping current network parameters:"
    echo "  SERVICE_HOST: $SERVICE_HOST"
    echo "  BRIDGE_IP: $BRIDGE_IP"
    echo "  PUBLIC_NETWORK_GATEWAY: $PUBLIC_NETWORK_GATEWAY"
    echo "  NETWORK_GATEWAY: $NETWORK_GATEWAY"
    echo "  IPV4_ADDRS_SAFE_TO_USE: $IPV4_ADDRS_SAFE_TO_USE"
    echo "  IPV6_ADDRS_SAFE_TO_USE: $IPV6_ADDRS_SAFE_TO_USE"
    echo "  FIXED_RANGE: $FIXED_RANGE"
    echo "  FLOATING_RANGE: $FLOATING_RANGE"
    echo "  SUBNETPOOL_PREFIX_V4: $SUBNETPOOL_PREFIX_V4"
    echo "  SUBNETPOOL_SIZE_V4: $SUBNETPOOL_SIZE_V4"
    echo "  SUBNETPOOL_V4_ID: $SUBNETPOOL_V4_ID"
    echo "  ROUTER_GW_IP: $ROUTER_GW_IP"
    echo "  TROVE_MGMT_SUBNET_RANGE: ${TROVE_MGMT_SUBNET_RANGE}"

    # Save xtrace setting
    local orig_xtrace
    orig_xtrace=$(set +o | grep xtrace)
    set -x

    echo "Creating Trove management network/subnet for Trove service project."
    trove_service_project_id=$(openstack project show $SERVICE_PROJECT_NAME -c id -f value)
    setup_mgmt_network ${trove_service_project_id} ${TROVE_MGMT_NETWORK_NAME} ${TROVE_MGMT_SUBNET_NAME} ${TROVE_MGMT_SUBNET_RANGE}
    mgmt_net_id=$(openstack network show ${TROVE_MGMT_NETWORK_NAME} -c id -f value)
    echo "Created Trove management network ${TROVE_MGMT_NETWORK_NAME}(${mgmt_net_id})"

    # Share the private network to other projects for testing purpose. We make
    # the private network accessible to control plane below so that we could
    # reach the private network for integration tests without floating ips
    # associated, no matter which user the tests are using.
    shared=$(openstack network show ${PRIVATE_NETWORK_NAME} -c shared -f value)
    if [[ "$shared" == "False" ]]; then
        openstack network set ${PRIVATE_NETWORK_NAME} --share
    fi
    sudo ip route replace ${IPV4_ADDRS_SAFE_TO_USE} via $ROUTER_GW_IP

    # Make sure we can reach the management port of the service VM, this
    # configuration is only for testing purpose. In production, it's
    # recommended to config the router in the cloud infrastructure for the
    # communication between Trove control plane and service VMs.
    INTERFACE=trove-mgmt
    MGMT_PORT_ID=$(openstack port create --project ${trove_service_project_id} --security-group ${TROVE_MGMT_SECURITY_GROUP} --device-owner trove --network ${TROVE_MGMT_NETWORK_NAME} --host=$(hostname) -c id -f value ${INTERFACE}-port)
    MGMT_PORT_MAC=$(openstack port show -c mac_address -f value $MGMT_PORT_ID)
    MGMT_PORT_IP=$(openstack port show -f value -c fixed_ips $MGMT_PORT_ID)
    MGMT_PORT_IP=${MGMT_PORT_IP//u\'/\'}
    MGMT_PORT_IP=$(echo ${MGMT_PORT_IP//\'/\"} | jq -r '.[0].ip_address')
    sudo ovs-vsctl -- --may-exist add-port ${OVS_BRIDGE:-br-int} $INTERFACE -- set Interface $INTERFACE type=internal -- set Interface $INTERFACE external-ids:iface-status=active -- set Interface $INTERFACE external-ids:attached-mac=$MGMT_PORT_MAC -- set Interface $INTERFACE external-ids:iface-id=$MGMT_PORT_ID -- set Interface $INTERFACE external-ids:skip_cleanup=true
    sudo ip link set dev $INTERFACE address $MGMT_PORT_MAC
    mask=$(echo ${TROVE_MGMT_SUBNET_RANGE} | awk -F'/' '{print $2}')
    sudo ip addr add ${MGMT_PORT_IP}/${mask} dev $INTERFACE
    sudo ip link set $INTERFACE up

    echo "Neutron network list:"
    openstack network list
    echo "Neutron subnet list:"
    openstack subnet list
    echo "Neutron router:"
    openstack router show ${ROUTER_ID} -f yaml
    echo "ip route:"
    sudo ip route

    # Now make sure the conf settings are right
    iniset $TROVE_CONF DEFAULT ip_regex ""
    iniset $TROVE_CONF DEFAULT black_list_regex ""
    iniset $TROVE_CONF DEFAULT management_networks ${mgmt_net_id}
    iniset $TROVE_CONF DEFAULT network_driver trove.network.neutron.NeutronDriver

    # Restore xtrace setting
    $orig_xtrace
}

function config_nova_keypair {
    export SSH_DIR=${SSH_DIR:-"$HOME/.ssh"}

    if [[ ! -f ${SSH_DIR}/id_rsa.pub ]]; then
        mkdir -p ${SSH_DIR}
        /usr/bin/ssh-keygen -f ${SSH_DIR}/id_rsa -q -N ""
        # This is to allow guest agent ssh into the controller in dev mode.
        cat ${SSH_DIR}/id_rsa.pub >> ${SSH_DIR}/authorized_keys
    else
        # This is to allow guest agent ssh into the controller in dev mode.
        cat ${SSH_DIR}/id_rsa.pub >> ${SSH_DIR}/authorized_keys
        sort ${SSH_DIR}/authorized_keys | uniq > ${SSH_DIR}/authorized_keys.uniq
        mv ${SSH_DIR}/authorized_keys.uniq ${SSH_DIR}/authorized_keys
        chmod 600 ${SSH_DIR}/authorized_keys
    fi

    echo "Creating Trove management keypair ${TROVE_MGMT_KEYPAIR_NAME}"
    openstack --os-region-name RegionOne --os-password ${SERVICE_PASSWORD} --os-project-name service --os-username trove \
      keypair create --public-key ${SSH_DIR}/id_rsa.pub ${TROVE_MGMT_KEYPAIR_NAME}

    iniset $TROVE_CONF DEFAULT nova_keypair ${TROVE_MGMT_KEYPAIR_NAME}
}

function config_cinder_volume_type {
    volume_type=$(openstack --os-region-name RegionOne --os-password ${SERVICE_PASSWORD} \
      --os-project-name service --os-username trove \
      volume type list -c Name -f value | awk 'NR==1 {print}')

    iniset $TROVE_CONF DEFAULT cinder_volume_type ${volume_type}
}

function config_mgmt_security_group {
    local sgid

    echo "Creating Trove management security group."
    sgid=$(openstack --os-region-name RegionOne --os-password ${SERVICE_PASSWORD} --os-project-name service --os-username trove security group create ${TROVE_MGMT_SECURITY_GROUP} -f value -c id)

    # Allow ICMP
    openstack --os-region-name RegionOne --os-password ${SERVICE_PASSWORD} --os-project-name service --os-username trove \
        security group rule create --proto icmp $sgid
    # Allow SSH
    openstack --os-region-name RegionOne --os-password ${SERVICE_PASSWORD} --os-project-name service --os-username trove \
        security group rule create --protocol tcp --dst-port 22 $sgid

    iniset $TROVE_CONF DEFAULT management_security_groups $sgid
}

# Dispatcher for trove plugin
if is_service_enabled trove; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Trove"
        install_trove
        install_python_troveclient
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        if is_service_enabled key; then
            create_trove_accounts
        fi

        echo_summary "Configuring Trove"
        configure_trove
    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        init_trove_db
        config_nova_keypair
        config_cinder_volume_type
        config_mgmt_security_group
        config_trove_network
        create_guest_image

        echo_summary "Starting Trove"
        start_trove

        # Guarantee the file permission in the trove code repo in order to
        # download trove code from trove-guestagent.
        sudo chown -R $STACK_USER:$STACK_USER "$DEST/trove"
    elif [[ "$1" == "stack" && "$2" == "test-config" ]]; then
        echo_summary "Configuring Tempest for Trove"
        configure_tempest_for_trove
    fi

    if [[ "$1" == "unstack" ]]; then
        stop_trove
        cleanup_trove
    fi
fi

# Restore xtrace
$XTRACE

# Tell emacs to use shell-script-mode
## Local variables:
## mode: shell-script
## End:
