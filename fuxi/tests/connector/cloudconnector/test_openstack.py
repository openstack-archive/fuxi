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

import mock

from fuxi.connector.cloudconnector import openstack
from fuxi import state_monitor
from fuxi import utils
from fuxi.tests import base, fake_client, fake_volume

from cinderclient import exceptions as cinder_exception
from novaclient import exceptions as nova_exception


class FakeNovaClient(object):
    class Volumes(object):
        def create_server_volume(self, volume_id):
            pass

        def delete_server_volume(self, server_id, volume_id):
            return None

    def __init__(self):
        self.volumes = self.Volumes()


def mock_monitor_cinder_volume(cls):
    return


def mock_not_found_volume(cls, volume_id):
    raise cinder_exception.ClientException(404)


def mock_delete_server_volume_execute_failed(cls, server_id, volume_id):
    raise nova_exception.ClientException(400)


def mock_instance_uuid():
    return '123'


def mock_list_with_attach_to_this(cls, search_opts={}):
    attachments = [{u'server_id': u'123',
                    u'attachment_id': u'123',
                    u'attached_at': u'2016-05-20T09:19:57.000000',
                    u'host_name': None,
                    u'device': None,
                    u'id': u'123'}]
    return [fake_volume.FakeCinderVolume(name='fake-vol1',
                                         attachments=attachments)]


def mock_list_with_attach_to_other(cls, search_opts={}):
    attachments = [{u'server_id': u'1234',
                    u'attachment_id': u'123',
                    u'attached_at': u'2016-05-20T09:19:57.000000',
                    u'host_name': None,
                    u'device': None,
                    u'id': u'123'}]
    return [fake_volume.FakeCinderVolume(name='fake-vol1',
                                         attachments=attachments)]


def mock_get_mountpoint_for_device(devpath, mountpoint):
    return ''


class TestCinderConnector(base.TestCase):
    def setUp(self):
        base.TestCase.setUp(self)
        self.connector = openstack.CinderConnector()
        self.connector.cinderclient = fake_client.FakeCinderClient()
        self.connector.novaclient = FakeNovaClient()

    def test_connect_volume(self):
        pass

    @mock.patch.object(utils, 'get_instance_uuid', mock_instance_uuid)
    @mock.patch.object(state_monitor.StateMonitor,
                       'monitor_cinder_volume',
                       mock_monitor_cinder_volume)
    def test_disconnect_volume(self):
        fake_cinder_volume = fake_volume.FakeCinderVolume()
        result = self.connector.disconnect_volume(fake_cinder_volume)
        self.assertIsNone(result)

    @mock.patch.object(fake_client.FakeCinderClient.Volumes,
                       'get',
                       mock_not_found_volume)
    @mock.patch.object(state_monitor.StateMonitor,
                       'monitor_cinder_volume',
                       mock_monitor_cinder_volume)
    def test_disconnect_volume_for_not_found(self):
        fake_cinder_volume = fake_volume.FakeCinderVolume()
        self.assertRaises(cinder_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    @mock.patch.object(FakeNovaClient.Volumes,
                       'delete_server_volume',
                       mock_delete_server_volume_execute_failed)
    @mock.patch.object(utils, 'get_instance_uuid', mock_instance_uuid)
    @mock.patch.object(state_monitor.StateMonitor,
                       'monitor_cinder_volume',
                       mock_monitor_cinder_volume)
    def test_disconnect_volume_for_delete_server_volume_failed(self):
        fake_cinder_volume = fake_volume.FakeCinderVolume()
        self.assertRaises(nova_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    def test_get_device_path(self):
        fake_cinder_volume = fake_volume.FakeCinderVolume()
        fake_devpath = ''.join(['/dev/disk/by-id/', fake_cinder_volume.id])
        self.assertEqual(fake_devpath,
                         self.connector.get_device_path(fake_cinder_volume))
