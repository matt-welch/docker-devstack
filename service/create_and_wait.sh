#!/bin/bash
function fn_isodate {
    date "+%Y-%M-%d %H:%M:%S"
}

function fn_wait_for_tenant {
    if [ "$DEBUG" == "off" ] ; then
        TENANT_NAME=$1
        TENANT_IP=""
        SECONDS=0
        while [ -z "$TENANT_IP" ] ; do 
            echo "Waiting for \"$TENANT_NAME\" to obtain an IP address..."
            TENANT_IP=$(openstack server show -f value -c addresses ${TENANT_NAME}  | cut -d "=" -f 2)
            sleep 0.1
        done
        echo "[$(fn_isodate)] $SECONDS s for OpenStack server API to return an IP address for $TENANT_IP"
        SECONDS=0
        sudo ip netns exec ${NETNS} ping -c 1 -W 1 $TENANT_IP
        while [ "$?" != 0 ] ; do
            sudo ip netns exec ${NETNS} ping -c 1 -W 1 $TENANT_IP > /dev/null
            sleep 0.1
        done
        sudo ip netns exec ${NETNS} ping -c 1 -W 1 $TENANT_IP
        echo "[$(fn_isodate)]  $SECONDS s for OpenStack server  \"$TENANT_IP\" to respond to ping"
        echo
    else
        echo "MOCKUP: waiting for server to oibtain an IP..."
        sleep 2 
    fi
    echo
}

function fn_create_instance {
        ID="$1"
        PARENT_NODE=$2
        ZONE=""
        SERVER_NAME=foo
        if [ -n "$2" ] ; then
            # specify zone if parent node is supplied
            PARENT_NODE="${2}"
            PARENT_NODE_ID=${PARENT_NODE#compute-}
            SERVER_NAME="tenant-${PARENT_NODE_ID}-${ID}"
            ZONE="--availability-zone nova:${PARENT_NODE}"
        fi
        echo "[$(fn_isodate)] Creating server instance ${SERVER_NAME} on host ${PARENT_NODE} with flavor ${FLAVOR}"
        if [ "$DEBUG" == "off" ] ; then
            openstack server create --flavor $FLAVOR --security-group $S3P_SEC_GRP --image $IMAGE $ZONE --nic net-id=$NETWORK_ID $SERVER_NAME
        fi
 
}

function fn_set_quotas {
    if [ "$DEBUG" == "off" ] ; then
        echo "[$(fn_isodate)] Setting OpenStack quotas..."
        openstack quota set --ports 400 --instances 200 --cores 200 demo
    fi
}

# defaults: 
FLAVOR="cirros256"
IMAGE="cirros-0.3.4-x86_64-uec"
DEBUG=off
S3P_SEC_GRP="s3p_secgrp"
SERVERS_PER_HOST=2
NETWORK_NAME=private
NETWORK_ID=$(openstack network list | grep $NETWORK_NAME | cut -d '|' -f 2 | tr -d ' ')
NETNS=$(ip netns ls | grep $NETWORK_ID)
fn_set_quotas
for (( TENANT_INDEX=1; TENANT_INDEX<=${SERVERS_PER_HOST} ; TENANT_INDEX++ )); do
    for HYPERVISOR in $(openstack hypervisor list | grep compute | cut -d '|' -f3 | tr -d ' '); do 
        fn_create_instance $TENANT_INDEX $HYPERVISOR 
        fn_wait_for_tenant $SERVER_NAME
    done
done

# vim: set et sw=4 ts=4 ai :
