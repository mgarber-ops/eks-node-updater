#!/usr/bin/python3

"""
AUTHOR: Matthew Garber
PURPOSE: CLI Application to facilitate EKS Managed Node Updates
"""

"""
Imports
"""

import boto3
import argparse
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import subprocess

"""
Globals
"""

"""
Client Connection
"""

eks_client = boto3.client('eks')

"""
# Define CLI arguments:
  # EKS Cluster Name
  # Force Update Boolean (Respect/Disregard Pod Disruption Budget Policies)
"""

parser = argparse.ArgumentParser(description='Pass in parameters for EKS Node Update')
parser.add_argument('--cluster-name', metavar='c', type=str, help='The name of your AWS EKS Cluster', required=True)
parser.add_argument('--force-update', metavar='f', type=bool, help='Force Node Updates and ignore Pod Disruption Budget?', required=True)
args = parser.parse_args()

""" 
 # Query Cluster Information:
 # Node Group Name
 # EKS Control Plane K8S Version
 # Node Group Release AMI Version
"""

def main():
    print ("Querying Node Data before Update...")
    query_nodes()
    # Add conditional error logic in event cluster doesn't exit/wrap in try&except
    cluster_query = eks_client.describe_cluster(
                name=args.cluster_name
                )
    eks_version = cluster_query['cluster']['version']
    print ("The Current K8S Version Running on EKS Cluster: " + args.cluster_name + " Is: " + eks_version)
    # REF on EKS Managed Node Groups only supporting 1.14+ -> https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html
    if float(eks_version) < 1.14:
        print ("The EKS Version doesn't support Managed Node Groups. Exiting")
        exit(1)
    else:
        print ("The EKS Version supports Managed Node Groups. Querying Managed Nodes...")

    mng = eks_client.list_nodegroups(clusterName=args.cluster_name)
    # Modify to support handling more than a single NG - We're making assumptions of a single NG per cluster.
    node_groups = mng['nodegroups']
    for node_group in node_groups:
        print ("EKS Cluster: " + args.cluster_name + " is leveraging managed node group: " + node_group)
        node_metadata = eks_client.describe_nodegroup(clusterName=args.cluster_name, nodegroupName=node_group)
        node_ami_version = node_metadata['nodegroup']['releaseVersion']
        node_eks_version = node_metadata['nodegroup']['version']
        print ("EKS Managed Node Group: " + node_group + " Is currently running AMI: " + node_ami_version + " and on EKS Version: " + node_eks_version)
        node_update(node_group, eks_version, node_ami_version)

""" 
Query Available Updates for a respective Managed Node Group
"""

def node_update(node_group, eks_version, node_ami_version):
    node_update = eks_client.update_nodegroup_version(clusterName=args.cluster_name, nodegroupName=node_group, version=eks_version, force=args.force_update)
    starttime = time.time()
    updated_node_version = node_update['update']['params'][0]['value']
    updated_node_ami = node_update['update']['params'][1]['value']
    node_update_id   = node_update['update']['id']
    if node_ami_version != updated_node_ami:
        print ("Executed Update for Node Group: " + node_group + " Parameters: " + "Latest AMI Version: " + updated_node_ami + " EKS Version: " + updated_node_version)
        print ("Update ID: " + node_update_id)
        node_update_check(node_group, node_update_id, starttime)
    else:
        print (node_group + " Is already running the latest AMI Version: " + updated_node_ami)
        exit(0)

"""
Execute Node Updates
"""

def node_update_check(node_group, node_update_id, starttime):
    update_check = eks_client.describe_update(name=args.cluster_name, updateId=node_update_id, nodegroupName=node_group)
    if update_check['update']['status'] == 'InProgress':
        print ("Still In Progress...")
        time.sleep(30)
        node_update_check(node_group, node_update_id, starttime)
    elif update_check['update']['status'] == 'Successful':
        endtime = time.time()
        print ("Update Complete. Total Duration: " + str(endtime-starttime) + " Seconds")
        query_nodes()
    elif update_check['update']['status'] == 'Failed' or 'Cancelled':
        print ("Update Failed or Cancelled: " + str(update_check['update']['errors']))
        exit(1)
"""
Connect to EKS Cluster and Query Node Information
"""

def query_nodes():
    get_kube_config()
    cfg = config.load_kube_config()
    api_instance = client.CoreV1Api(cfg)
    node_data = api_instance.list_node(pretty='true')
    for data in node_data.items:
        print ("Node: " + data.metadata.name + " Is running version: " + data.status.node_info.kubelet_version)
"""
Leverage AWS CLI to Auth to EKS Cluster for K8S Client
"""
def get_kube_config():
    clicall = 'aws eks update-kubeconfig --name '+args.cluster_name
    kube_config = subprocess.run([clicall], shell=True, check=True)

if __name__== "__main__":
  main()
