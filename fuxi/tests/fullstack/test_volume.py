# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


#from fuxi.lib import utils as lib_utils
from fuxi.tests.fullstack import fuxi_base
from fuxi import utils


class VolumeTest(fuxi_base.FuxiBaseTest):
    """Test Volumes operation

    Test volumes creation/deletion from docker to Cinder
    """
    def test_create_delete_volume_with_fuxi_driver(self):
        """Create and Delete docker volume with Fuxi

           This method creates a docker volume with Fuxi driver
           and tests it was created in Cinder.
           It then deletes the docker volume and tests that it was
           deleted from Cinder.
        """
        #fake_ipam = {
        #    "Driver": "kuryr",
        #    "Options": {},
        #    "Config": [
        #        {
        #            "Subnet": "10.0.0.0/16",
        #            "IPRange": "10.0.0.0/24",
        #            "Gateway": "10.0.0.1"
        #        }
        #    ]
        #}
        #net_name = lib_utils.get_random_string(8)
        res = self.docker_client.create_volume(name=net_name, driver='fuxi',
                                                ipam=fake_ipam)
        vol_id = res['Id']
        try:
            network = self.cinder_client.list_volumes(
                tags=utils.make_net_tags(vol_id))
        except Exception as e:
            self.docker_client.remove_volume(vol_id)
            message = ("Failed to list cinder volumes: %s")
            self.fail(message % e.args[0])
        self.assertEqual(1, len(network['volumes']))
        self.docker_client.remove_network(vol_id)
        volume = self.cinder_client.list_volumes(
            tags=utils.make_net_tags(vol_id))
        self.assertEqual(0, len(volume['volumes']))

    def test_create_delete_volume_without_fuxi_driver(self):
        """Create and Delete docker volume without Fuxi

           This method create a docker network with the default
           docker driver, It tests that it was created correctly, but
           not added to Neutron
        """
        vol_name = lib_utils.get_random_string(8)
        res = self.docker_client.create_volume(name=vol_name)
        vol_id = res['Id']
        volume = self.cinder_client.list_volumes(
            tags=utils.make_net_tags(vol_id))
        self.assertEqual(0, len(volume['volumes']))
        docker_volumes = self.docker_client.volumes()
        volume_found = False
        for docker_vol in docker_volumes:
            if docker_vol['Id'] == vol_id:
                volume_found = True
        self.assertTrue(volume_found)
        self.docker_client.remove_volume(vol_id)

    #def test_create_network_with_same_name(self):
    #    """Create docker network with same name

    #       Create two docker networks with same name,
    #       delete them and see that neutron networks are
    #       deleted as well
    #    """
    #    fake_ipam_1 = {
    #        "Driver": "kuryr",
    #        "Options": {},
    #        "Config": [
    #            {
    #                "Subnet": "10.1.0.0/16",
    #                "IPRange": "10.1.0.0/24",
    #                "Gateway": "10.1.0.1"
    #            }
    #        ]
    #    }
    #    fake_ipam_2 = {
    #        "Driver": "kuryr",
    #        "Options": {},
    #        "Config": [
    #            {
    #                "Subnet": "10.2.0.0/16",
    #                "IPRange": "10.2.0.0/24",
    #                "Gateway": "10.2.0.1"
    #            }
    #        ]
    #    }
    #    net_name = lib_utils.get_random_string(8)
    #    res = self.docker_client.create_network(name=net_name, driver='kuryr',
    #                                            ipam=fake_ipam_1)
    #    net_id1 = res['Id']

    #    res = self.docker_client.create_network(name=net_name, driver='kuryr',
    #                                            ipam=fake_ipam_2)
    #    net_id2 = res['Id']
    #    try:
    #        network = self.neutron_client.list_networks(
    #            tags=utils.make_net_tags(net_id1))
    #        self.assertEqual(1, len(network['networks']))
    #        network = self.neutron_client.list_networks(
    #            tags=utils.make_net_tags(net_id2))
    #        self.assertEqual(1, len(network['networks']))
    #    except Exception as e:
    #        self.docker_client.remove_network(net_id1)
    #        self.docker_client.remove_network(net_id2)
    #        message = ("Failed to list neutron networks: %s")
    #        self.fail(message % e.args[0])
    #    self.docker_client.remove_network(net_id1)
    #    self.docker_client.remove_network(net_id2)
    #    network = self.neutron_client.list_networks(
    #        tags=utils.make_net_tags(net_id1))
    #    self.assertEqual(0, len(network['networks']))
    #    network = self.neutron_client.list_networks(
    #        tags=utils.make_net_tags(net_id2))
    #    self.assertEqual(0, len(network['networks']))
