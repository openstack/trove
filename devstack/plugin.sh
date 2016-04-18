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

        if [[ "$KEYSTONE_CATALOG_BACKEND" = 'sql' ]]; then

            local trove_service=$(get_or_create_service "trove" \
                "database" "Trove Service")
            get_or_create_endpoint $trove_service \
                "$REGION_NAME" \
                "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s" \
                "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s" \
                "http://$SERVICE_HOST:8779/v1.0/\$(tenant_id)s"
        fi
    fi
}

# stack.sh entry points
# ---------------------

# cleanup_trove() - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_trove {
    #Clean up dirs
    rm -fr $TROVE_AUTH_CACHE_DIR/*
    rm -fr $TROVE_CONF_DIR/*
}


# configure_trove() - Set config files, create data dirs, etc
function configure_trove {
    setup_develop $TROVE_DIR

    # Create the trove conf dir and cache dirs if they don't exist
    sudo install -d -o $STACK_USER ${TROVE_CONF_DIR} ${TROVE_AUTH_CACHE_DIR}

    # Copy api-paste file over to the trove conf dir
    cp $TROVE_LOCAL_API_PASTE_INI $TROVE_API_PASTE_INI

    # (Re)create trove conf files
    rm -f $TROVE_CONF
    rm -f $TROVE_TASKMANAGER_CONF
    rm -f $TROVE_CONDUCTOR_CONF

    iniset $TROVE_CONF DEFAULT rabbit_userid $RABBIT_USERID
    iniset $TROVE_CONF DEFAULT rabbit_password $RABBIT_PASSWORD
    iniset $TROVE_CONF database connection `database_connection_url trove`
    iniset $TROVE_CONF DEFAULT default_datastore $TROVE_DATASTORE_TYPE
    setup_trove_logging $TROVE_CONF
    iniset $TROVE_CONF DEFAULT trove_api_workers "$API_WORKERS"

    # Increase default quota.
    iniset $TROVE_CONF DEFAULT max_accepted_volume_size 10
    iniset $TROVE_CONF DEFAULT max_instances_per_user 10
    iniset $TROVE_CONF DEFAULT max_volumes_per_user 10

    configure_auth_token_middleware $TROVE_CONF trove $TROVE_AUTH_CACHE_DIR

    # (Re)create trove taskmanager conf file if needed
    if is_service_enabled tr-tmgr; then
        TROVE_AUTH_ENDPOINT=$KEYSTONE_AUTH_URI/v$IDENTITY_API_VERSION

        iniset $TROVE_TASKMANAGER_CONF DEFAULT rabbit_userid $RABBIT_USERID
        iniset $TROVE_TASKMANAGER_CONF DEFAULT rabbit_password $RABBIT_PASSWORD
        iniset $TROVE_TASKMANAGER_CONF database connection `database_connection_url trove`
        iniset $TROVE_TASKMANAGER_CONF DEFAULT taskmanager_manager trove.taskmanager.manager.Manager
        iniset $TROVE_TASKMANAGER_CONF DEFAULT nova_proxy_admin_user radmin
        iniset $TROVE_TASKMANAGER_CONF DEFAULT nova_proxy_admin_tenant_name trove
        iniset $TROVE_TASKMANAGER_CONF DEFAULT nova_proxy_admin_pass $RADMIN_USER_PASS
        iniset $TROVE_TASKMANAGER_CONF DEFAULT trove_auth_url $TROVE_AUTH_ENDPOINT
        setup_trove_logging $TROVE_TASKMANAGER_CONF

        # Increase default timeouts (required by the tests).
        iniset $TROVE_TASKMANAGER_CONF DEFAULT agent_call_high_timeout 300
        iniset $TROVE_TASKMANAGER_CONF DEFAULT usage_timeout 1200
    fi

    # (Re)create trove conductor conf file if needed
    if is_service_enabled tr-cond; then
        iniset $TROVE_CONDUCTOR_CONF DEFAULT rabbit_userid $RABBIT_USERID
        iniset $TROVE_CONDUCTOR_CONF DEFAULT rabbit_password $RABBIT_PASSWORD
        iniset $TROVE_CONDUCTOR_CONF database connection `database_connection_url trove`
        iniset $TROVE_CONDUCTOR_CONF DEFAULT nova_proxy_admin_user radmin
        iniset $TROVE_CONDUCTOR_CONF DEFAULT nova_proxy_admin_tenant_name trove
        iniset $TROVE_CONDUCTOR_CONF DEFAULT nova_proxy_admin_pass $RADMIN_USER_PASS
        iniset $TROVE_CONDUCTOR_CONF DEFAULT trove_auth_url $TROVE_AUTH_ENDPOINT
        iniset $TROVE_CONDUCTOR_CONF DEFAULT control_exchange trove
        setup_trove_logging $TROVE_CONDUCTOR_CONF
    fi

    # Set up Guest Agent conf
    iniset $TROVE_GUESTAGENT_CONF DEFAULT rabbit_userid $RABBIT_USERID
    iniset $TROVE_GUESTAGENT_CONF DEFAULT rabbit_host $TROVE_HOST_GATEWAY
    iniset $TROVE_GUESTAGENT_CONF DEFAULT rabbit_password $RABBIT_PASSWORD
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
}

# install_python_troveclient() - Collect source and prepare
function install_python_troveclient {
    if use_library_from_git "python-troveclient"; then
        git_clone $TROVECLIENT_REPO $TROVECLIENT_DIR $TROVECLIENT_BRANCH
        setup_develop $TROVECLIENT_DIR
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
    get_or_create_project ${ALT_TENANT_NAME} default
    get_or_create_user ${ALT_USERNAME} "$ADMIN_PASSWORD" "default" "alt_demo@example.com"
    get_or_add_user_project_role Member ${ALT_USERNAME} ${ALT_TENANT_NAME}

    # The second part adds an admin user to the tenant.
    ADMIN_ALT_USERNAME=${ADMIN_ALT_USERNAME:-admin_${ALT_USERNAME}}
    get_or_create_user ${ADMIN_ALT_USERNAME} "$ADMIN_PASSWORD" "default" "admin_alt_demo@example.com"
    get_or_add_user_project_role admin ${ADMIN_ALT_USERNAME} ${ALT_TENANT_NAME}

    # If no guest image is specified, skip remaining setup
    [ -z "$TROVE_GUEST_IMAGE_URL" ] && return 0

    # Find the glance id for the trove guest image
    # The image is uploaded by stack.sh -- see $IMAGE_URLS handling
    GUEST_IMAGE_NAME=$(basename "$TROVE_GUEST_IMAGE_URL")
    GUEST_IMAGE_NAME=${GUEST_IMAGE_NAME%.*}
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
}

# finalize_trove_network() - do the last thing(s) before starting Trove
function finalize_trove_network {
    management_network_id=$(neutron --os-tenant-name admin --os-username admin --os-password $ADMIN_PASSWORD net-list | grep $PRIVATE_NETWORK_NAME | awk '{print $2}')

    echo "finalize_trove_network: found network id $management_network_id"

    iniset $TROVE_CONF DEFAULT network_label_regex .*
    iniset $TROVE_CONF DEFAULT ip_regex .*
    iniset $TROVE_CONF DEFAULT black_list_regex ^10.0.1.*
    iniset $TROVE_CONF DEFAULT default_neutron_networks $management_network_id
    iniset $TROVE_CONF DEFAULT network_driver trove.network.neutron.NeutronDriver

    iniset $TROVE_TASKMANAGER_CONF DEFAULT network_driver trove.network.neutron.NeutronDriver
    iniset $TROVE_TASKMANAGER_CONF mysql tcp_ports 22,3306
}

# start_trove() - Start running processes, including screen
function start_trove {
    run_process tr-api "$TROVE_BIN_DIR/trove-api --config-file=$TROVE_CONF --debug"
    run_process tr-tmgr "$TROVE_BIN_DIR/trove-taskmanager --config-file=$TROVE_TASKMANAGER_CONF --debug"
    run_process tr-cond "$TROVE_BIN_DIR/trove-conductor --config-file=$TROVE_CONDUCTOR_CONF --debug"
}

# stop_trove() - Stop running processes
function stop_trove {
    # Kill the trove screen windows
    local serv
    for serv in tr-api tr-tmgr tr-cond; do
        stop_process $serv
    done
}

# Dispatcher for trove plugin
if is_service_enabled trove; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Trove"
        install_trove
        install_python_troveclient
        cleanup_trove
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
    fi
fi

# Restore xtrace
$XTRACE

# Tell emacs to use shell-script-mode
## Local variables:
## mode: shell-script
## End:
