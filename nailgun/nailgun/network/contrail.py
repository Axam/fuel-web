# -*- coding: utf-8 -*-

#    Copyright 2013 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nailgun.db import db
from nailgun.network.manager import NetworkManager


class ContrailManager(NetworkManager):
#    NETWORK = 'contrail'

    @classmethod
    def update(cls, cluster, network_configuration):
        cls.update_networks(cluster, network_configuration)

        if 'net_manager' in network_configuration:
            setattr(
                cluster,
                'net_manager',
                network_configuration['net_manager']
            )
        if 'dns_nameservers' in network_configuration:
            setattr(
                cluster,
                'dns_nameservers',
                network_configuration['dns_nameservers']['nameservers']
            )
        db().commit()

    @classmethod
    def generate_vlan_ids_list(cls, data, cluster, ng):
        if ng.get("vlan_start") is None:
            return []
        return range(int(ng.get("vlan_start")),
                     int(ng.get("vlan_start")) + int(ng.get("amount")))


#    def assign_networks_contrail(self, node):
#        self.clear_assigned_networks(node)
#        # exclude admin interface if it is not the only interface
#        ifaces = [iface for iface in node.interfaces
#                  if iface.id != node.admin_interface.id]
#        if not ifaces:
#            ifaces = [node.admin_interface]
#        # assign all remaining networks
#        for ng in self.get_cluster_networkgroups_by_node(node):
#            ifaces[0].assigned_networks.append(ng)
#
#        node.admin_interface.assigned_networks.append(
#            self.get_admin_network_group()
#        )
#
#        db().commit()

