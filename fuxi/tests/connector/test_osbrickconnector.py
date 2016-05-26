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
import platform
import socket
import sys

from fuxi.common import constants
from fuxi.connector import osbrickconnector
from fuxi.tests import base, fake_client, fake_object
from fuxi import utils

from cinderclient import exceptions as cinder_exception

from oslo_concurrency import processutils


def mock_get_connector_properties(multipath=False, enforce_multipath=False):
    props = {}
    props['host'] = socket.gethostname()
    props['initiator'] = 'iqn.1993-08.org.debian:01:b57cc344932'
    props['platform'] = platform.machine()
    props['os_type'] = sys.platform
    return props


def mock_list_with_attach_to_this(cls, search_opts={}):
    attachments = [{u'server_id': u'123',
                    u'attachment_id': u'123',
                    u'attached_at': u'2016-05-20T09:19:57.000000',
                    u'host_name': utils.get_hostname(),
                    u'device': None,
                    u'id': u'123'}]
    return [fake_object.FakeCinderVolume(name='fake-vol1',
                                         attachments=attachments)]


def mock_list_with_attach_to_other(cls, search_opts={}):
    attachments = [{u'server_id': u'123',
                    u'attachment_id': u'123',
                    u'attached_at': u'2016-05-20T09:19:57.000000',
                    u'host_name': utils.get_hostname() + u'other',
                    u'device': None,
                    u'id': u'123'}]
    return [fake_object.FakeCinderVolume(name='fake-vol1',
                                         attachments=attachments)]


def mock_get_mountpoint_for_device(devpath, mountpoint):
    return ''


class TestCinderConnector(base.TestCase):
    def setUp(self):
        base.TestCase.setUp(self)
        self.connector = osbrickconnector.CinderConnector()
        self.connector.cinderclient = fake_client.FakeCinderClient()

    def test_connect_volume(self):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        self.connector._connect_volume = mock.MagicMock()

        self.connector.connect_volume(fake_cinder_volume)
        self.assertEqual(1, len(fake_cinder_volume.attachments))

    @mock.patch.object(osbrickconnector, 'brick_get_connector',
                       return_value=fake_client.FakeOSBrickConnector())
    def test_disconnect_volume(self, mock_brick_connector):
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]
        fake_cinder_volume = \
            fake_object.FakeCinderVolume(attachments=attachments)

        self.connector._get_connection_info = mock.MagicMock()
        self.connector.cinderclient.volumes.detach = mock.MagicMock()
        self.assertIsNone(self.connector.disconnect_volume(fake_cinder_volume))

    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes'
                '.initialize_connection',
                side_effect=cinder_exception.ClientException(500))
    def test_disconnect_volume_no_connection_info(self, mock_init_conn):
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]
        fake_cinder_volume = \
            fake_object.FakeCinderVolume(attachments=attachments)
        self.assertRaises(cinder_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes'
                '.initialize_connection',
                side_effect=processutils.ProcessExecutionError())
    def test_disconnect_volume_osbrick_disconnect_failed(self, mock_init_conn):
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]
        fake_cinder_volume = \
            fake_object.FakeCinderVolume(attachments=attachments)
        self.assertRaises(processutils.ProcessExecutionError,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.detach',
                side_effect=cinder_exception.ClientException(500))
    @mock.patch.object(osbrickconnector, 'brick_get_connector',
                       return_value=fake_client.FakeOSBrickConnector())
    @mock.patch.object(osbrickconnector.CinderConnector,
                       '_get_connection_info',
                       return_value={'driver_volume_type': 'fake_proto',
                                     'data': {'path': '/dev/0'}})
    def test_disconnect_volume_detach_failed(self, mock_detach,
                                             mock_brick_connector,
                                             mock_conn_info):
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]
        fake_cinder_volume = \
            fake_object.FakeCinderVolume(attachments=attachments)
        self.assertRaises(cinder_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)

    def test_get_device_path(self):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        self.assertEqual(os.path.join(constants.VOLUME_LINK_DIR,
                                      fake_cinder_volume.id),
                         self.connector.get_device_path(fake_cinder_volume))
