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
import platform
import socket
import sys

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


def mock_initialize_connection_failed(cls, volume, connector):
    raise cinder_exception.ClientException(500)


def mock_osbrick_disconnect_failed(cls, connector, conntor):
    raise processutils.ProcessExecutionError


def mock_detach_failed(cls, volume_id, attachment_uuid):
    raise cinder_exception.ClientException(500)


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
    @mock.patch.object(osbrickconnector,
                       'brick_get_connector_properties',
                       mock_get_connector_properties)
    def setUp(self):
        base.TestCase.setUp(self)
        self.connector = osbrickconnector.CinderConnector()
        self.connector.cinderclient = fake_client.FakeCinderClient()

    def test_connect_volume(self):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        self.connector._connect_volume = mock.MagicMock()

        self.connector.connect_volume(fake_cinder_volume)
        self.assertEqual(1, len(fake_cinder_volume.attachments))

    def test_disconnect_volume(self):
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]
        fake_cinder_volume = \
            fake_object.FakeCinderVolume(attachments=attachments)

        self.connector._get_connection_info = mock.MagicMock()
        self.connector.osbrickconnector.disconnect_volume = mock.MagicMock()
        self.connector.cinderclient.volumes.detach = mock.MagicMock()
        self.assertIsNone(self.connector.disconnect_volume(fake_cinder_volume))

    @mock.patch.object(fake_client.FakeCinderClient.Volumes,
                       'initialize_connection',
                       mock_initialize_connection_failed)
    def test_disconnect_volume_error_with_no_connection_info(self):
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

    @mock.patch.object(fake_client.FakeCinderClient.Volumes,
                       'initialize_connection',
                       mock_osbrick_disconnect_failed)
    def test_disconnect_volume_error_with_osbrick_disconnect_failed(self):
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

    @mock.patch.object(fake_client.FakeCinderClient.Volumes,
                       'detach',
                       mock_detach_failed)
    def test_disconnect_volume_error_with_detach_failed(self):
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]
        fake_cinder_volume = \
            fake_object.FakeCinderVolume(attachments=attachments)
        self.connector.osbrickconnector.disconnect_volume = mock.MagicMock()
        self.assertRaises(cinder_exception.ClientException,
                          self.connector.disconnect_volume,
                          fake_cinder_volume)
