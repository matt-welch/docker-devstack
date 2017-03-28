#!/bin/sh
# On docker run, Env Variables "STACK_PASS & SERVICE_HOST" should be set using -e
#  example 'docker run -e "STACK_PASS=stack" -e "SERVICE_HOST=192.168.0.5" compute'
# or overided below by uncommenting:
set -o nounset # throw an error if a variable is unset to prevent unexpected behaviors
STACK_PASS="stack"
SERVICE_HOST=${SERVICE_HOST:-192.168.3.2}
# ODL_NETWORK should be set in the 'docker run' script
ODL_NETWORK=${ODL_NETWORK}
DEVSTACK_HOME="/home/stack/devstack"
CONF_PATH=$DEVSTACK_HOME/local.conf
BRANCH_NAME=stable/newton
TAG_NAME="origin/${BRANCH_NAME}"

#Set Nameserver to google
[ -z "$(grep "8.8.8.8" /etc/resolv.conf )" ] && echo nameserver 8.8.8.8 | sudo tee -a /etc/resolv.conf

# change the stack user password
echo "stack:$STACK_PASS" | sudo chpasswd

# get container IP
ip=`/sbin/ip -o -4 addr list eth0 | awk '{print $4}' | cut -d/ -f1`
[ -z "$( echo $no_proxy | grep "$(hostname)" )" ] && export no_proxy="${no_proxy},$(hostname)"
[ -z "$( echo $no_proxy | grep "${ip}" )" ] && export no_proxy="${no_proxy},${ip}"
[ -z "$( echo $no_proxy | grep "${SERVICE_HOST}" )" ] && export no_proxy="${no_proxy},${SERVICE_HOST}"

# fix address binding issue in mysql
sudo sed -i 's:^bind-address.*:#&:' /etc/mysql/my.cnf

# allow services to start
sudo sed -i 's:^exit .*:exit 0:' /usr/sbin/policy-rc.d

# remove any dead screen sessions from previous stacking
screen -wipe

# set the correct branch in devstack
cd $DEVSTACK_HOME
[ -z "$(git branch -a | grep "* ${BRANCH_NAME}")" ] && \
	git fetch && \
	git checkout -b ${BRANCH_NAME} -t ${TAG_NAME}

# copy local.conf into devstack and customize, based on environment including:
# ODL_NETWORK, ip, DEVSTACK_HOME, SERVICE_HOST
cp /home/stack/local.conf $CONF_PATH

# Configure local.conf
# update the ip of this host
sed -i "s:\(HOST_IP=\).*:\1${ip}:" $CONF_PATH
sed -i "s:\(SERVICE_HOST=\).*:\1${ip}:" $CONF_PATH
# modify the local.conf according to ODL_NETWORK value
echo "Preparing $CONF_PATH for ODL=$ODL_NETWORK"
echo
if [ "$ODL_NETWORK" = "False" ] ; then
    # prepare local.conf to NOT use ODL networking (default to Neutron)
    sed -i "s:^#\(enable_service q-agt\).*:\1:g" $CONF_PATH
    sed -i "s:^\(enable_plugin networking-odl\):#\1:g" $CONF_PATH
    sed -i "s:^\(Q_ML2_PLUGIN_MECHANISM_DRIVERS=opendaylight\).*:#\1:g" $CONF_PATH
    sed -i "s:^\(mechanism_drivers=\).*:\1openvswitch:g" $CONF_PATH
else
    # prepare local.conf to use ODL networking
    sed -i "s:^\(enable_service q-agt\):#\1:g" $CONF_PATH
    sed -i "s:^#\(enable_plugin networking-odl\):\1:g" $CONF_PATH
    sed -i "s:^#\(Q_ML2_PLUGIN_MECHANISM_DRIVERS=opendaylight\).*:\1:g" $CONF_PATH
fi

# begin stacking
$DEVSTACK_HOME/stack.sh

# write a marker file to indicate successful stacking
if [ $? = 0 ] ; then
    echo "$(hostname) stacking successful at $(date)" >> stacking.status
    /home/stack/devstack/tools/info.sh >> stacking.status
fi

# vim: set et ts=4 sw=4 :

