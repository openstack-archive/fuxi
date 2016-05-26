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
import os

from fuxi.common import constants
from fuxi.common import state_monitor
from fuxi.connector.cloudconnector import openstack
from fuxi import utils
from fuxi.tests import base, fake_client, fake_object

from cinderclient import exceptions as cinder_exception
from novaclient import exceptions as nova_exception


def mock_list_with_attach_to_this(cls, search_opts={}):
    attachments = [{u'server_id': u'123',
                    u'attachment_id': u'123',
                    u'attached_at': u'2016-05-20T09:19:57.000000',
                    u'host_name': None,
                    u'device': None,
                    u'id': u'123'}]
    return [fake_object.FakeCinderVolume(name='fake-vol1',
                                         attachments=attachments)]


def mock_list_with_attach_to_other(cls, search_opts={}):
    attachments = [{u'server_id': u'1234',
                    u'attachment_id': u'123',
                    u'attached_at': u'2016-05-20T09:19:57.000000',
                    u'host_name': None,
                    u'device': None,
                    u'id': u'123'}]
    return [fake_object.FakeCinderVolume(name='fake-vol1',
                                         attachments=attachments)]


def mock_get_mountpoint_for_device(devpath, mountpoint):
    return ''


class TestCinderConnector(base.TestCase):
    def setUp(self):
        base.TestCase.setUp(self)
        self.connector = openstack.CinderConnector()
        self.connector.cinderclient = fake_client.FakeCinderClient()
        self.connector.novaclient = fake_client.FakeNovaClient()

    def test_connect_volume(self):
        pass

    @mock.patch.object(utils, 'get_instance_uuid', return_value='fake-123')
    @mock.patch.object(state_monitor.StateMonitor, 'monitor_cinder_volume',
                       return_value=None)
    def test_disconnect_volume(self, mock_inst_id, mock_monitor):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        result = self.connector.disconnect_volume(fake_cinder_volume)
        self.assertIsNone(result)

    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.get',
                side_effect=cinder_exception.ClientException(404))
    @mock.patch.object(state_monitor.StateMonitor,
                       'monitor_cinder_volume')
    def test_disconnect_volume_for_not_found(self, mock_get, mocK_monitor):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        self.assertRaises(cinder_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    @mock.patch('fuxi.tests.fake_client.FakeNovaClient.Volumes'
                '.delete_server_volume',
                side_effect=nova_exception.ClientException(500))
    @mock.patch.object(utils, 'get_instance_uuid', return_value='fake-123')
    @mock.patch.object(state_monitor.StateMonitor,
                       'monitor_cinder_volume')
    def test_disconnect_volume_for_delete_server_volume_failed(self,
                                                               mock_delete,
                                                               mock_inst_id,
                                                               mock_monitor):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        self.assertRaises(nova_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    def test_get_device_path(self):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        fake_devpath = os.path.join(constants.VOLUME_LINK_DIR,
                                    fake_cinder_volume.id)
        self.assertEqual(fake_devpath,
                         self.connector.get_device_path(fake_cinder_volume))
