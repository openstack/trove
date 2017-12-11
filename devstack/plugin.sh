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

        create_service_user "trove"

        local trove_service=$(get_or_create_service "trove" \
            "database" "Trove Service")
        get_or_create_endpoint $trove_service \
            "$REGION_NAME" \
            "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s" \
            "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s" \
            "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s"
    fi
}

# _cleanup_trove_apache_wsgi - Removes all the WSGI related files and
# restart apache.
function _cleanup_trove_apache_wsgi {
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
        _cleanup_trove_apache_wsgi
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

# _config_trove_apache_wsgi() - Setup WSGI config files for Trove and
# enable the site
function _config_trove_apache_wsgi {
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
    tail_log trove-access /var/log/${APACHE_NAME}/trove-api-access.log
    tail_log trove-api /var/log/${APACHE_NAME}/trove-api.log
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

    # Copy the default policy file over to the trove conf dir
    cp $TROVE_LOCAL_POLICY_JSON $TROVE_POLICY_JSON

    # (Re)create trove conf files
    rm -f $TROVE_CONF
    rm -f $TROVE_TASKMANAGER_CONF
    rm -f $TROVE_CONDUCTOR_CONF

    TROVE_AUTH_ENDPOINT=$KEYSTONE_AUTH_URI/v$IDENTITY_API_VERSION

    # (Re)create trove api conf file if needed
    if is_service_enabled tr-api; then
        # Set common configuration values (but only if they're defined)
        iniset_conditional $TROVE_CONF DEFAULT max_accepted_volume_size $TROVE_MAX_ACCEPTED_VOLUME_SIZE
        iniset_conditional $TROVE_CONF DEFAULT max_instances_per_tenant $TROVE_MAX_INSTANCES_PER_TENANT
        iniset_conditional $TROVE_CONF DEFAULT max_volumes_per_tenant $TROVE_MAX_VOLUMES_PER_TENANT

        iniset $TROVE_CONF DEFAULT rpc_backend "rabbit"
        iniset $TROVE_CONF DEFAULT control_exchange trove
        iniset $TROVE_CONF oslo_messaging_rabbit rabbit_hosts $RABBIT_HOST
        iniset $TROVE_CONF oslo_messaging_rabbit rabbit_password $RABBIT_PASSWORD
        iniset $TROVE_CONF oslo_messaging_rabbit rabbit_userid $RABBIT_USERID


        iniset $TROVE_CONF database connection `database_connection_url trove`
        iniset $TROVE_CONF DEFAULT default_datastore $TROVE_DATASTORE_TYPE
        setup_trove_logging $TROVE_CONF
        iniset $TROVE_CONF DEFAULT trove_api_workers "$API_WORKERS"

        configure_auth_token_middleware $TROVE_CONF trove
        iniset $TROVE_CONF DEFAULT trove_auth_url $TROVE_AUTH_ENDPOINT
    fi

    # configure apache related files
    if [[ "${TROVE_USE_MOD_WSGI}" == "TRUE" ]]; then
        echo "Configuring Trove to use mod-wsgi and Apache"
        _config_trove_apache_wsgi
    fi

    # (Re)create trove taskmanager conf file if needed
    if is_service_enabled tr-tmgr; then
        # Use these values only if they're set
        iniset_conditional $TROVE_TASKMANAGER_CONF DEFAULT agent_call_low_timeout $TROVE_AGENT_CALL_LOW_TIMEOUT
        iniset_conditional $TROVE_TASKMANAGER_CONF DEFAULT agent_call_high_timeout $TROVE_AGENT_CALL_HIGH_TIMEOUT
        iniset_conditional $TROVE_TASKMANAGER_CONF DEFAULT resize_time_out $TROVE_RESIZE_TIME_OUT
        iniset_conditional $TROVE_TASKMANAGER_CONF DEFAULT usage_timeout $TROVE_USAGE_TIMEOUT
        iniset_conditional $TROVE_TASKMANAGER_CONF DEFAULT state_change_wait_time $TROVE_STATE_CHANGE_WAIT_TIME

        iniset $TROVE_TASKMANAGER_CONF DEFAULT rpc_backend "rabbit"
        iniset $TROVE_TASKMANAGER_CONF DEFAULT control_exchange trove
        iniset $TROVE_TASKMANAGER_CONF oslo_messaging_rabbit rabbit_hosts $RABBIT_HOST
        iniset $TROVE_TASKMANAGER_CONF oslo_messaging_rabbit rabbit_password $RABBIT_PASSWORD
        iniset $TROVE_TASKMANAGER_CONF oslo_messaging_rabbit rabbit_userid $RABBIT_USERID

        iniset $TROVE_TASKMANAGER_CONF database connection `database_connection_url trove`
        iniset $TROVE_TASKMANAGER_CONF DEFAULT taskmanager_manager trove.taskmanager.manager.Manager
        iniset $TROVE_TASKMANAGER_CONF DEFAULT nova_proxy_admin_user radmin
        iniset $TROVE_TASKMANAGER_CONF DEFAULT nova_proxy_admin_tenant_name trove
        iniset $TROVE_TASKMANAGER_CONF DEFAULT nova_proxy_admin_pass $RADMIN_USER_PASS
        iniset $TROVE_TASKMANAGER_CONF DEFAULT trove_auth_url $TROVE_AUTH_ENDPOINT

        iniset $TROVE_TASKMANAGER_CONF cassandra tcp_ports 22,7000,7001,7199,9042,9160
        iniset $TROVE_TASKMANAGER_CONF couchbase tcp_ports 22,8091,8092,4369,11209-11211,21100-21199
        iniset $TROVE_TASKMANAGER_CONF couchdb tcp_ports 22,5984
        iniset $TROVE_TASKMANAGER_CONF db2 tcp_ports 22,50000
        iniset $TROVE_TASKMANAGER_CONF mariadb tcp_ports 22,3306,4444,4567,4568
        iniset $TROVE_TASKMANAGER_CONF mongodb tcp_ports 22,2500,27017,27019
        iniset $TROVE_TASKMANAGER_CONF mysql tcp_ports 22,3306
        iniset $TROVE_TASKMANAGER_CONF percona tcp_ports 22,3306
        iniset $TROVE_TASKMANAGER_CONF postgresql tcp_ports 22,5432
        iniset $TROVE_TASKMANAGER_CONF pxc tcp_ports 22,3306,4444,4567,4568
        iniset $TROVE_TASKMANAGER_CONF redis tcp_ports 22,6379,16379
        iniset $TROVE_TASKMANAGER_CONF vertica tcp_ports 22,5433,5434,5444,5450,4803

        setup_trove_logging $TROVE_TASKMANAGER_CONF
    fi

    # (Re)create trove conductor conf file if needed
    if is_service_enabled tr-cond; then
        iniset $TROVE_CONDUCTOR_CONF DEFAULT rpc_backend "rabbit"
        iniset $TROVE_CONDUCTOR_CONF oslo_messaging_rabbit rabbit_hosts $RABBIT_HOST
        iniset $TROVE_CONDUCTOR_CONF oslo_messaging_rabbit rabbit_password $RABBIT_PASSWORD
        iniset $TROVE_CONDUCTOR_CONF oslo_messaging_rabbit rabbit_userid $RABBIT_USERID

        iniset $TROVE_CONDUCTOR_CONF database connection `database_connection_url trove`
        iniset $TROVE_CONDUCTOR_CONF DEFAULT nova_proxy_admin_user radmin
        iniset $TROVE_CONDUCTOR_CONF DEFAULT nova_proxy_admin_tenant_name trove
        iniset $TROVE_CONDUCTOR_CONF DEFAULT nova_proxy_admin_pass $RADMIN_USER_PASS
        iniset $TROVE_CONDUCTOR_CONF DEFAULT trove_auth_url $TROVE_AUTH_ENDPOINT
        iniset $TROVE_CONDUCTOR_CONF DEFAULT control_exchange trove

        setup_trove_logging $TROVE_CONDUCTOR_CONF
    fi

    # Use these values only if they're set
    iniset_conditional $TROVE_GUESTAGENT_CONF DEFAULT state_change_wait_time $TROVE_STATE_CHANGE_WAIT_TIME
    iniset_conditional $TROVE_GUESTAGENT_CONF DEFAULT command_process_timeout $TROVE_COMMAND_PROCESS_TIMEOUT

    # Set up Guest Agent conf
    iniset $TROVE_GUESTAGENT_CONF DEFAULT rpc_backend "rabbit"
    iniset $TROVE_GUESTAGENT_CONF oslo_messaging_rabbit rabbit_password $RABBIT_PASSWORD
    iniset $TROVE_GUESTAGENT_CONF oslo_messaging_rabbit rabbit_userid $RABBIT_USERID
    iniset $TROVE_GUESTAGENT_CONF oslo_messaging_rabbit rabbit_hosts $TROVE_HOST_GATEWAY

    iniset $TROVE_GUESTAGENT_CONF DEFAULT nova_proxy_admin_user radmin
    iniset $TROVE_GUESTAGENT_CONF DEFAULT nova_proxy_admin_tenant_name trove
    iniset $TROVE_GUESTAGENT_CONF DEFAULT nova_proxy_admin_pass $RADMIN_USER_PASS
    iniset $TROVE_GUESTAGENT_CONF DEFAULT trove_auth_url $TROVE_AUTH_ENDPOINT
    iniset $TROVE_GUESTAGENT_CONF DEFAULT control_exchange trove
    iniset $TROVE_GUESTAGENT_CONF DEFAULT ignore_users os_admin
    iniset $TROVE_GUESTAGENT_CONF DEFAULT log_dir /var/log/trove/
    iniset $TROVE_GUESTAGENT_CONF DEFAULT log_file trove-guestagent.log

    setup_trove_logging $TROVE_GUESTAGENT_CONF
}

# install_trove() - Collect source and prepare
function install_trove {
    setup_develop $TROVE_DIR

    if [[ "${TROVE_USE_MOD_WSGI}" == "TRUE" ]]; then
        echo "Installing apache wsgi"
        install_apache_wsgi
    fi

    if is_service_enabled horizon; then
        install_trove_dashboard
    fi
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

# init_trove() - Initializes Trove Database as a Service
function init_trove {
    # (Re)Create trove db
    recreate_database trove

    # Initialize the trove database
    $TROVE_MANAGE db_sync

    # Add an admin user to the 'tempest' alt_demo tenant.
    # This is needed to test the guest_log functionality.
    # The first part mimics the tempest setup, so make sure we have that.
    ALT_USERNAME=${ALT_USERNAME:-alt_demo}
    ALT_TENANT_NAME=${ALT_TENANT_NAME:-alt_demo}
    ALT_TENANT_ID=$(get_or_create_project ${ALT_TENANT_NAME} default)
    get_or_create_user ${ALT_USERNAME} "$ADMIN_PASSWORD" "default" "alt_demo@example.com"
    get_or_add_user_project_role Member ${ALT_USERNAME} ${ALT_TENANT_NAME}

    # The second part adds an admin user to the tenant.
    ADMIN_ALT_USERNAME=${ADMIN_ALT_USERNAME:-admin_${ALT_USERNAME}}
    get_or_create_user ${ADMIN_ALT_USERNAME} "$ADMIN_PASSWORD" "default" "admin_alt_demo@example.com"
    get_or_add_user_project_role admin ${ADMIN_ALT_USERNAME} ${ALT_TENANT_NAME}
    # Now add these credentials to the clouds.yaml file
    ADMIN_ALT_DEMO_CLOUD=devstack-alt-admin
    CLOUDS_YAML=${CLOUDS_YAML:-/etc/openstack/clouds.yaml}
    $TOP_DIR/tools/update_clouds_yaml.py \
        --file ${CLOUDS_YAML} \
        --os-cloud ${ADMIN_ALT_DEMO_CLOUD} \
        --os-region-name ${REGION_NAME} \
        --os-identity-api-version 3 \
        ${CA_CERT_ARG} \
        --os-auth-url ${KEYSTONE_AUTH_URI} \
        --os-username ${ADMIN_ALT_USERNAME} \
        --os-password ${ADMIN_PASSWORD} \
        --os-project-name ${ALT_TENANT_NAME}

    # If no guest image is specified, skip remaining setup
    [ -z "$TROVE_GUEST_IMAGE_URL" ] && return 0

    # Find the glance id for the trove guest image
    # The image is uploaded by stack.sh -- see $IMAGE_URLS handling
    GUEST_IMAGE_NAME=$(basename "$TROVE_GUEST_IMAGE_URL")
    GUEST_IMAGE_NAME=${GUEST_IMAGE_NAME%.*}

    TOKEN=$(openstack token issue -c id -f value)
    TROVE_GUEST_IMAGE_ID=$(openstack --os-token $TOKEN --os-url $GLANCE_SERVICE_PROTOCOL://$GLANCE_HOSTPORT image list | grep "${GUEST_IMAGE_NAME}" | get_field 1)
    if [ -z "$TROVE_GUEST_IMAGE_ID" ]; then
        # If no glance id is found, skip remaining setup
        echo "Datastore ${TROVE_DATASTORE_TYPE} will not be created: guest image ${GUEST_IMAGE_NAME} not found."
        return 1
    fi

    # Now that we have the guest image id, initialize appropriate datastores / datastore versions
    $TROVE_MANAGE datastore_update "$TROVE_DATASTORE_TYPE" ""
    $TROVE_MANAGE datastore_version_update "$TROVE_DATASTORE_TYPE" "$TROVE_DATASTORE_VERSION" "$TROVE_DATASTORE_TYPE" \
        "$TROVE_GUEST_IMAGE_ID" "$TROVE_DATASTORE_PACKAGE" 1
    $TROVE_MANAGE datastore_version_update "$TROVE_DATASTORE_TYPE" "inactive_version" "inactive_manager" "$TROVE_GUEST_IMAGE_ID" "" 0
    $TROVE_MANAGE datastore_update "$TROVE_DATASTORE_TYPE" "$TROVE_DATASTORE_VERSION"
    $TROVE_MANAGE datastore_update "Inactive_Datastore" ""

    # Some datastores provide validation rules.
    # if one is provided, configure it.
    if [ -f "${TROVE_DIR}/trove/templates/${TROVE_DATASTORE_TYPE}"/validation-rules.json ]; then
        echo "Configuring validation rules for ${TROVE_DATASTORE_TYPE}"
        $TROVE_MANAGE db_load_datastore_config_parameters \
            "$TROVE_DATASTORE_TYPE" "$TROVE_DATASTORE_VERSION" \
            "${TROVE_DIR}/trove/templates/${TROVE_DATASTORE_TYPE}"/validation-rules.json
    fi
}

# Create private IPv4 subnet
# Note: This was taken from devstack:lib/neutron_plugins/services/l3 and will need to be maintained
function _create_private_subnet_v4 {
    local project_id=$1
    local net_id=$2
    local name=${3:-$PRIVATE_SUBNET_NAME}
    local os_cloud=${4:-devstack-admin}

    local subnet_params="--project $project_id "
    subnet_params+="--ip-version 4 "
    if [[ -n "$NETWORK_GATEWAY" ]]; then
        subnet_params+="--gateway $NETWORK_GATEWAY "
    fi
    if [ -n $SUBNETPOOL_V4_ID ]; then
        subnet_params+="--subnet-pool $SUBNETPOOL_V4_ID "
    else
        subnet_params+="--subnet-range $FIXED_RANGE "
    fi
    subnet_params+="--network $net_id $name"
    local subnet_id
    subnet_id=$(openstack --os-cloud $os_cloud --os-region "$REGION_NAME" subnet create $subnet_params | grep ' id ' | get_field 2)
    die_if_not_set $LINENO subnet_id "Failure creating private IPv4 subnet for $project_id"
    echo $subnet_id
}

# Create private IPv6 subnet
# Note: This was taken from devstack:lib/neutron_plugins/services/l3 and will need to be maintained
function _create_private_subnet_v6 {
    local project_id=$1
    local net_id=$2
    local name=${3:-$IPV6_PRIVATE_SUBNET_NAME}
    local os_cloud=${4:-devstack-admin}

    die_if_not_set $LINENO IPV6_RA_MODE "IPV6 RA Mode not set"
    die_if_not_set $LINENO IPV6_ADDRESS_MODE "IPV6 Address Mode not set"
    local ipv6_modes="--ipv6-ra-mode $IPV6_RA_MODE --ipv6-address-mode $IPV6_ADDRESS_MODE"
    local subnet_params="--project $project_id "
    subnet_params+="--ip-version 6 "
    if [[ -n "$IPV6_PRIVATE_NETWORK_GATEWAY" ]]; then
        subnet_params+="--gateway $IPV6_PRIVATE_NETWORK_GATEWAY "
    fi
    if [ -n $SUBNETPOOL_V6_ID ]; then
        subnet_params+="--subnet-pool $SUBNETPOOL_V6_ID "
    else
        subnet_params+="--subnet-range $FIXED_RANGE_V6 $ipv6_modes} "
    fi
    subnet_params+="--network $net_id $name "
    local ipv6_subnet_id
    ipv6_subnet_id=$(openstack --os-cloud $os_cloud --os-region "$REGION_NAME" subnet create $subnet_params | grep ' id ' | get_field 2)
    die_if_not_set $LINENO ipv6_subnet_id "Failure creating private IPv6 subnet for $project_id"
    echo $ipv6_subnet_id
}

# Set up a network on the alt_demo tenant.  Requires ROUTER_ID, REGION_NAME and IP_VERSION to be set
function set_up_network() {
    local CLOUD_USER=$1
    local PROJECT_ID=$2
    local NET_NAME=$3
    local SUBNET_NAME=$4
    local IPV6_SUBNET_NAME=$5

    NEW_NET_ID=$(openstack --os-cloud ${CLOUD_USER} --os-region "$REGION_NAME" network create --project ${PROJECT_ID} "$NET_NAME" | grep ' id ' | get_field 2)
    if [[ "$IP_VERSION" =~ 4.* ]]; then
        NEW_SUBNET_ID=$(_create_private_subnet_v4 ${PROJECT_ID} ${NEW_NET_ID} ${SUBNET_NAME} ${CLOUD_USER})
        openstack --os-cloud ${CLOUD_USER} --os-region "$REGION_NAME" router add subnet $ROUTER_ID $NEW_SUBNET_ID
    fi
    if [[ "$IP_VERSION" =~ .*6 ]]; then
        NEW_IPV6_SUBNET_ID=$(_create_private_subnet_v6 ${PROJECT_ID} ${NEW_NET_ID} ${IPV6_SUBNET_NAME} ${CLOUD_USER})
        openstack --os-cloud ${CLOUD_USER} --os-region "$REGION_NAME" router add subnet $ROUTER_ID $NEW_IPV6_SUBNET_ID
    fi

    echo $NEW_NET_ID
}

# finalize_trove_network() - do the last thing(s) before starting Trove
function finalize_trove_network {

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

    # Create the net/subnet for the alt_demo tenant so the int-tests have a proper network
    echo "Creating network/subnets for ${ALT_TENANT_NAME} project"
    ALT_PRIVATE_NETWORK_NAME=${TROVE_PRIVATE_NETWORK_NAME}
    ALT_PRIVATE_SUBNET_NAME=${TROVE_PRIVATE_SUBNET_NAME}
    ALT_PRIVATE_IPV6_SUBNET_NAME=ipv6-${ALT_PRIVATE_SUBNET_NAME}
    ALT_NET_ID=$(set_up_network $ADMIN_ALT_DEMO_CLOUD $ALT_TENANT_ID $ALT_PRIVATE_NETWORK_NAME $ALT_PRIVATE_SUBNET_NAME $ALT_PRIVATE_IPV6_SUBNET_NAME)
    echo "Created network ${ALT_PRIVATE_NETWORK_NAME} (${ALT_NET_ID})"

    # Set up a management network to test that functionality
    ALT_MGMT_NETWORK_NAME=trove-mgmt
    ALT_MGMT_SUBNET_NAME=${ALT_MGMT_NETWORK_NAME}-subnet
    ALT_MGMT_IPV6_SUBNET_NAME=ipv6-${ALT_MGMT_SUBNET_NAME}
    ALT_MGMT_ID=$(set_up_network $ADMIN_ALT_DEMO_CLOUD $ALT_TENANT_ID $ALT_MGMT_NETWORK_NAME $ALT_MGMT_SUBNET_NAME $ALT_MGMT_IPV6_SUBNET_NAME)
    echo "Created network ${ALT_MGMT_NETWORK_NAME} (${ALT_MGMT_ID})"

    # Make sure we can reach the VMs
    local replace_range=${SUBNETPOOL_PREFIX_V4}
    if [[ -z "${SUBNETPOOL_V4_ID}" ]]; then
        replace_range=${FIXED_RANGE}
    fi
    sudo ip route replace $replace_range via $ROUTER_GW_IP

    echo "Neutron network list:"
    openstack --os-cloud devstack-admin --os-region "$REGION_NAME" network list

    # Now make sure the conf settings are right
    iniset $TROVE_CONF DEFAULT network_label_regex "${ALT_PRIVATE_NETWORK_NAME}"
    iniset $TROVE_CONF DEFAULT ip_regex ""
    iniset $TROVE_CONF DEFAULT black_list_regex ""
    # Don't use a default network for now, until the neutron issues are figured out
    #iniset $TROVE_CONF DEFAULT default_neutron_networks "${ALT_MGMT_ID}"
    iniset $TROVE_CONF DEFAULT default_neutron_networks ""
    iniset $TROVE_CONF DEFAULT network_driver trove.network.neutron.NeutronDriver

    iniset $TROVE_TASKMANAGER_CONF DEFAULT network_label_regex "${ALT_PRIVATE_NETWORK_NAME}"
    iniset $TROVE_TASKMANAGER_CONF DEFAULT ip_regex ""
    iniset $TROVE_TASKMANAGER_CONF DEFAULT black_list_regex ""
    # Don't use a default network for now, until the neutron issues are figured out
    #iniset $TROVE_TASKMANAGER_CONF DEFAULT default_neutron_networks "${ALT_MGMT_ID}"
    iniset $TROVE_CONF DEFAULT default_neutron_networks ""
    iniset $TROVE_TASKMANAGER_CONF DEFAULT network_driver trove.network.neutron.NeutronDriver
}

# start_trove() - Start running processes, including screen
function start_trove {
    if [[ ${TROVE_USE_MOD_WSGI}" == TRUE" ]]; then
        echo "Restarting Apache server ..."
        enable_apache_site trove-api
        restart_apache_server
    else
        run_process tr-api "$TROVE_BIN_DIR/trove-api --config-file=$TROVE_CONF --debug"
    fi
    run_process tr-tmgr "$TROVE_BIN_DIR/trove-taskmanager --config-file=$TROVE_TASKMANAGER_CONF --debug"
    run_process tr-cond "$TROVE_BIN_DIR/trove-conductor --config-file=$TROVE_CONDUCTOR_CONF --debug"
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

# Dispatcher for trove plugin
if is_service_enabled trove; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Trove"
        install_trove
        install_python_troveclient
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configuring Trove"
        configure_trove

        if is_service_enabled key; then
            create_trove_accounts
        fi

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        # Initialize trove
        init_trove

        # finish the last step in trove network configuration
        echo_summary "Finalizing Trove Network Configuration"

        if is_service_enabled neutron; then
            echo "finalize_trove_network: Neutron is enabled."
            finalize_trove_network
        else
            echo "finalize_trove_network: Neutron is not enabled. Nothing to do."
        fi

        # Start the trove API and trove taskmgr components
        echo_summary "Starting Trove"
        start_trove
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
