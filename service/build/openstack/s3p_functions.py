#!/usr/bin/env python
import s3p_openstack_tools as s3p
from datetime import datetime
import argparse
import sys
import os
from time import sleep

debug_mode=True
verbosity_level=0
network_list=[]
subnet_list=[]
hypervisor_list=[]
server_list=[]
validate_existing = True

def isodate():
    """prints the date in a pseudo-ISO format (Y-M-D H:M:S)"""
    d = datetime.now()
    return d.isoformat()

def debug_print(stringIn=''):
    """docstring for dbgPrint"""
    if debug_mode:
        print(stringIn)

def logprint(message):
    """prints a message in 'log format' like '[date] message' """
    print("[{0}] {1}".format(isodate(), message))

def get_auth_args_openstackrc():
    """ This function should source an openstackrc file for auth_args """
    pass

def get_auth_args():
    service_host_ip = os.getenv('SERVICE_HOST')
    auth_args = {
        'auth_url': 'http://' + service_host_ip + ':5000/v2.0',
        'project_name': 'demo',
        'username': 'admin',
        'password': 'secret',
    }
    return auth_args

def create_instance(conn, instance_name, hypervisor_name, network_name,
        resource_ids, smoketest=True):
    """
    Creates an S3P server (OpenStack tenant instance) on the specified
    hypervisor, attached to a specific network
    """
    global validate_existing
    # print("validate_existing = {0}".format(validate_existing))
    global server_list
    """ check if instance is already created """
    if not(instance_name in server_list):
        # create instance
        logprint("Creating server {0} on host {1}, network {2}".format(
            instance_name, hypervisor_name, network_name))
        t1=datetime.now()
        os_instance = s3p.create_server_raw(conn, instance_name, hypervisor_name,
                network_name, resource_ids['image_id'],
                resource_ids['flavor_id'], s3p_defaults['secgrp_name']
                )
        t2=datetime.now()
        type(os_instance)
        print os_instance

        if False:   #os_instance == None:
            logprint("ERROR: Server creation failed for:\nserver name: {0}".format(
                instance_name))
            sys.exit(1)
        else:
            logprint("Server Creation took {1} seconds".format(isodate(),
                (t2-t1).total_seconds()))
    else:
        os_instance = conn.compute.find_server(instance_name)
        logprint("WARNING: An instance with name '{0}'".format(instance_name) +
            "already exists, skipping creation")
        smoketest = validate_existing

    if smoketest:
        os_network = conn.network.find_network(network_name)
        smoke_test_server(conn, os_instance, os_network)

def smoke_test_server(conn, os_instance, os_network):
    """
    Smoke Test == ping new OpenStack tenant instance until it responds 
    a.k.a. wait_for_tenant
    This smoke test enters the DHCP network namespace (netns) on the service
    host that corresponds to the server's network
    """
    logprint("Waiting for instance {0} to respond to ping on network {1}...".format(
        os_instance.name, os_network.name))
    t1 =datetime.now()
    """ timing: get instance IP address and network_id """
    NETNS = 'qdhcp-' + os_network.id
    ip_addr = os_instance.addresses[os_network.name][0]['addr']
    logprint("Server '{0}' obtained IPV4 address: {1}".format(os_instance.name, ip_addr))
    """ enter netns and ping instance IP """
    command  = "ip netns exec qdhcp-" + os_network.id + " ping -c 1 " + os_instance.addresses[os_network.name][0]['addr']
    print("Smoke test: {0}".format(command))
    """ TODO: This smoke test is very coarse - could be much better"""
    response = os.system(command)
    while response != 0:
        sleep(0.1)
        response = os.system(command)
    """ timing: enter netns & ping server until it responds """
    t2=datetime.now()
    """ print/accumulate timing info for server boot & smoke test """
    logprint("SmokeTest: {0} seconds for tenant '{1}' to respond to ping".format(
        (t2-t1).total_seconds(), os_instance.name))

def delete_instance(conn, instance_name):
    """ Deletes an S3P server (OpenStack tenant instance) """
    logprint("Deleting instance \"{0}\"".format(instance_name))
    s3p.delete_server(conn, instance_name)

"""  network management functions """
def determine_net_index(comp_id, num_networks, host_id, numberingType='one_net'):
    """Function determines which network will be used"""
    if numberingType == 'modulo_num_networks':
        networkIdx = comp_id % num_networks
    elif numberingType == 'one_per_physhost':
        networkIdx = host_id
    else:
        """ one network to rule them all """
        networkIdx = 0
    return networkIdx

def create_security_group_and_rules(conn, secgrp_name):
    """creates s3p security group and adds rules for SSH and ICMP """
    os_security_group = conn.network.find_security_group(secgrp_name)
    if os_security_group == None:
        logprint("Creating security group {0}".format(secgrp_name))
        os_security_group = s3p.create_security_group(conn, secgrp_name)
        s3p.add_security_group_rules_ssh(conn, os_security_group.id)
        s3p.add_security_group_rules_icmp(conn, os_security_group.id)
    else:
        logprint("Using existing security group '{0}'".format(secgrp_name))
    return os_security_group

def create_network_and_subnet(conn, network_name, network_ix):
    """creates an openstack network and subnet"""
    global network_list
    if not(network_name in network_list):
        logprint("Creating OpenStack network with name: {0}".format(network_name))
        os_network = s3p.create_network_raw(conn, network_name)
        if os_network != None:
            subnet_name = network_name+'-sub'
            parent_network_id = os_network.id
            cidr = '10.0.'+str(network_ix)+'.0/24'
            gateway_ip = '10.0.'+str(network_ix)+'.1'
            logprint("Creating OpenStack subnet with name: {0}".format(network_name+"-sub"))
            os_subnet = s3p.create_subnet_raw(
                    conn,
                    subnet_name,
                    parent_network_id,
                    cidr,
                    gateway_ip)
            # TODO: attach subnet to router
        else:
            logprint("ERROR: Failed to create openstack network '{0}'".format(
                network_name))
            sys.exit(1)
    else:
        logprint("WARNING: an OpenStack network named '{0}' already exists - skipping creation.".format(
            network_name))
        os_network = conn.network.find_network(network_name)
    return os_network.id

def delete_network_and_subnet(conn, os_network):
    """
    Deletes a network and its associated subnets
    Each network should have a list of subnets associated with it through
    OpenStack or through a global variable herein
    """
    name = os_network.name
    logprint("Deleting network \"{0}\"".format(name))
    # TODO: remove router interface to network
    s3p.delete_network(conn, os_network)
    logprint("Network \"{0}\" Successfully deleted".format(name))

def remove_router_interface_to_network(conn, network_name, router_name='router1'):
    pass

def set_quotas(conn):
    """sets OpenStack quotas for scale testing"""
    logprint("Setting quotas for OpenStack")

# cleanup
def cleanup(conn):
    """removes all allocated OpenStack resources incl. servers, networks, subnets"""
    global server_list
    global network_list
    # delete servers
    # server_list = s3p.list_servers_by_name(conn)
    # for server_name in server_list:
    #     delete_instance(conn, server_name)
    # server_list = []
    # list comprehension to delete all s3p servers ('tenant-')
    [ delete_instance(conn, server.id) for server in conn.compute.servers()
            if s3p_defaults['server_prefix'] in server.name ]
    server_list = s3p.list_servers_by_name(conn)

    # delete networks
    # network_list = s3p.list_networks_by_name(conn)
    # for network_name in network_list:
    #     delete_network_and_subnet(conn, network_name)
    # network_list = []
    # use a list comprehension to delete the s3p networks.  It's scary, but works beautifully
    [ delete_network_and_subnet(conn, network) for network in conn.network.networks()
            if s3p_defaults['network_prefix'] in network.name ]
    network_list  = s3p.list_networks_by_name(conn)

# COMPLETED:
def unit_tests(conn):
    """ tests functions defined here or in s3p_openstack_tools """
    """
    The following functions are working:
    """
    # List compute resources
    # s3p.list_servers(conn)
    # list_servers(conn)
    # list_images(conn)
    # s3p.list_flavors(conn)
    # list_keypairs(conn)
    s3p.list_images(conn)
    s3p.list_servers(conn)
    node_id="21-11"
    compute_host="compute-"+node_id
    server_name="tenant-"+node_id+"-1"
    logprint("{0}, {1}".format(compute_host, server_name))
    s3p.create_server(conn, server_name, compute_host)

    # List network resources
    s3p.list_networks(conn)
    print("")
    s3p.list_subnets(conn)
    print("")
    s3p.list_security_groups(conn)
    print("")
    s3p.list_network_agents(conn)
    print("")
    s3p.list_net_availability_zones(conn)
    print("")
    s3p.list_comp_availability_zones(conn)
    print("")

    # create a network:
    s3p.create_network(conn, network_name)

    # delete a network & it's subnets:
    s3p.delete_network(conn, network_name)

def get_resource_ids(conn, names):
    """gets resource identifiers (OpenStack resource IDs) for default resources"""
    # get security group id
    defaults = {'secgrp_id': None, 'image_id': None, 'flavor_id': None}
    os_secgrp = conn.network.find_security_group(names['secgrp_name'])
    defaults['secgrp_id'] = os_secgrp.id
    # get image id
    os_image = conn.compute.find_image(names['image_name'])
    defaults['image_id'] = os_image.id
    # get flavor id
    os_flavor = conn.compute.find_flavor(names['flavor_name'])
    defaults['flavor_id'] = os_flavor.id

    if debug_mode:
        logprint("{0}: {1}".format(names['secgrp_name'], defaults['secgrp_id']))
        logprint("{0}: {1}".format(names['image_name'], defaults['image_id']))
        logprint("{0}: {1}".format(names['flavor_name'], defaults['flavor_id']))
    return defaults

def parse_ids_from_hypervisor_name(hypervisor_name):
    """
    Returns component identifiers from a provided hyperfisor name
    example: for hypervisor 'compute-5-11', this function will return two
    strings: host_id=5 and comp_id=11
    """
    host_id = hypervisor_name.split('-')[1]
    comp_id = hypervisor_name.split('-')[2]
    return host_id, comp_id

def one_shot_create(conn):
    """ use a specific hypervisor """
    # phys_host_id = 5
    # comp_id = 11
    # hypervisor_ID = str(phys_host_id) + '-' + str(comp_id)
    # hypervisor_name = 'compute-' + hypervisor_ID

    num_networks = 1
    servers_per_host = 1
    net_numbering_type = 'one_per_physhost'
    # only create one tenant per host for now
    instance_name = 'tenant-' + hypervisor_ID + '-1'
    network_ix = determine_net_index(
            comp_id,
            num_networks,
            phys_host_id,
            net_numbering_type)
    network_name = 's3p-net-' + str(network_ix)

    network_id = create_network_and_subnet(conn,
            network_name,
            network_ix)

    create_instance(conn,
            instance_name,
            hypervisor_name,
            network_id)

    delete_instance(conn, instance_name)
"""
" main testing loop
"""
def main():
    global network_list
    global subnet_list
    global hypervisor_list
    global server_list
    global debug_mode
    global s3p_defaults

    """
    parse input args with argparse
    input args:
    --cleanup - deletes all s3p-created instances and networks
    --debug - enables debug_mode
    operation - arguments to describe how many networks, servers, etc are created
      operation['num_networks']
      operation['num_servers']
      operation['servers_per_host']
      ...
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--cleanup",
        help="cleanup cluster by deleting all instances and networks",
        action="store_true")
    parser.add_argument("-d", "--debug",
        help="enable debug mode which increases output",
        action="store_true")
    args = parser.parse_args()

    debug_print("args.cleanup = {0}".format(args.cleanup))
    debug_print("args.debug = {0}".format(args.debug))
    debug_mode = args.debug
    cleanup_mode = args.cleanup

    logprint("Obtaining OpenStack credentials")
    conn = s3p.get_openstack_connection()

    s3p_defaults = {'secgrp_name': 's3p_secgrp',
            'image_name': 'cirros-0.3.4-x86_64-uec',
            'flavor_name': 'cirros256',
            'network_prefix': 's3p-net-',
            'server_prefix': 'tenant-'
            }

    s3p_resource_ids = get_resource_ids(conn, s3p_defaults)

    if cleanup_mode:
        # cleanup resources
        # TODO: ask user if they REALLY want to delete all the servers and networks in the cluster
        cleanup(conn)
    else:
        """ Assumptions:
            quotas and s3p_secgrp are alreay created
        set_quotas(conn)
        create_security_group(conn, s3p_defaults.secgrp_name)
        """
        # get list of networks by name
        network_list = s3p.list_networks_by_name(conn)
        debug_print(logprint("Network list: {0}".format(network_list)))

        # get list of hypervisors by name
        hypervisor_list = s3p.list_hypervisors_by_name(conn)
        debug_print(logprint("Hypervisor List: {0}".format(hypervisor_list)))

        # get list of servers by name
        server_list = s3p.list_servers_by_name(conn)
        debug_print(logprint("Server List: {0}".format(server_list)))

        servers_per_host = 1
        max_networks = len(hypervisor_list)
        net_numbering_type = 'one_per_physhost'

        # instance_name = 'tenant-' + hypervisor_ID + '-1'
        # network_ix = determine_net_index(
        #     comp_id,
        #     max_networks,
        #     phys_host_id,
        #     net_numbering_type)
        # network_name = 's3p-net-' + str(network_ix)

        # network_id = create_network_and_subnet(conn,
        #     network_name,
        #     network_ix)

        # create_instance(conn,
        #     instance_name,
        #     hypervisor_name,
        #     network_id)

        # delete_instance(conn, instance_name)

        # loop through hypervisors, creating tenants on each
        for hypervisor_name in hypervisor_list:
            phys_host_id, comp_id = parse_ids_from_hypervisor_name(hypervisor_name)

            network_ix = determine_net_index(
                comp_id,
                max_networks,
                phys_host_id,
                net_numbering_type)

            network_name = 's3p-net-' + str(network_ix)

            network_id = create_network_and_subnet(conn,
                network_name,
                network_ix)

            hypervisor_ID = phys_host_id + "-" + comp_id
            # only create one tenant per host for now
            instance_name = 'tenant-' + hypervisor_ID + "-1"
            create_instance(conn,
                instance_name,
                hypervisor_name,
                network_name,
                s3p_resource_ids)


        # subnet_list = s3p.list_subnets(conn)
        # hypervisor_list = s3p.list_hypervisors(conn)
        # server_list = s3p.list_servers(conn)

    logprint("Done")


if __name__ == '__main__':
    main()

