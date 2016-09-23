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
from fuxi.common import mount
from fuxi.common import state_monitor
from fuxi.connector import osbrickconnector
from fuxi.tests.unit import base, fake_client, fake_object
from fuxi import exceptions
from fuxi import utils

from cinderclient import exceptions as cinder_exception
from manilaclient.openstack.common.apiclient import exceptions \
    as manila_exception
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
    @mock.patch.object(utils, 'execute')
    def test_disconnect_volume(self, mock_brick_connector, mock_execute):
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

    @mock.patch.object(osbrickconnector, 'brick_get_connector_properties',
                       mock_get_connector_properties)
    @mock.patch.object(utils, 'execute')
    @mock.patch('fuxi.tests.unit.fake_client.FakeCinderClient.Volumes'
                '.initialize_connection',
                side_effect=cinder_exception.ClientException(500))
    def test_disconnect_volume_no_connection_info(self, mock_execute,
                                                  mock_init_conn):
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

    @mock.patch.object(osbrickconnector, 'brick_get_connector',
                       return_value=fake_client.FakeOSBrickConnector())
    @mock.patch.object(osbrickconnector.CinderConnector,
                       '_get_connection_info',
                       return_value={'driver_volume_type': 'fake_proto',
                                     'data': {'path': '/dev/0'}})
    @mock.patch.object(utils, 'execute')
    @mock.patch('fuxi.tests.unit.fake_client.FakeOSBrickConnector'
                '.disconnect_volume',
                side_effect=processutils.ProcessExecutionError())
    def test_disconnect_volume_osbrick_disconnect_failed(self, mock_connector,
                                                         mock_init_conn,
                                                         mock_execute,
                                                         mock_disconnect_vol):
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

    @mock.patch('fuxi.tests.unit.fake_client.FakeCinderClient.Volumes.detach',
                side_effect=cinder_exception.ClientException(500))
    @mock.patch.object(osbrickconnector, 'brick_get_connector',
                       return_value=fake_client.FakeOSBrickConnector())
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(osbrickconnector.CinderConnector,
                       '_get_connection_info',
                       return_value={'driver_volume_type': 'fake_proto',
                                     'data': {'path': '/dev/0'}})
    def test_disconnect_volume_detach_failed(self, mock_detach,
                                             mock_brick_connector,
                                             mock_execute,
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


class TestManilaConncetor(base.TestCase):
    def setUp(self):
        base.TestCase.setUp(self)
        self._set_connector()

    @mock.patch.object(utils, 'get_manilaclient',
                       return_value=fake_client.FakeManilaClient())
    def _set_connector(self, mock_client):
        self.connector = osbrickconnector.ManilaConnector()
        self.connector.manilaclient = fake_client.FakeManilaClient()
        self.connector._get_brick_connector = mock.MagicMock()
        self.connector._get_brick_connector.return_value \
            = fake_client.FakeOSBrickConnector()

    def test_check_access_allowed(self):
        fake_share = fake_object.FakeManilaShare(share_proto='UNKNOWN')
        self.assertFalse(self.connector.check_access_allowed(fake_share))

        fake_share = fake_object.FakeManilaShare(share_proto='NFS')
        self.assertFalse(self.connector.check_access_allowed(fake_share))

        fake_al = [fake_object.FakeShareAccess(access_type='ip',
                                               access_to='192.168.0.1',
                                               state='active')]
        with mock.patch('fuxi.tests.unit.fake_client.FakeManilaClient.Shares'
                        '.access_list',
                        return_value=fake_al):
            with mock.patch.object(self.connector, '_get_access_to',
                                   return_value='192.168.0.1'):
                self.assertTrue(
                    self.connector.check_access_allowed(fake_share))

    def test_connect_volume(self):
        fake_share = fake_object.FakeManilaShare(share_proto='NFS')
        self.connector._get_access_to = mock.MagicMock()
        self.connector._get_access_to.return_value = '192.168.0.2'
        with mock.patch.object(state_monitor.StateMonitor,
                               'monitor_share_access'):
            self.assertEqual(fake_share.export_location,
                             self.connector.connect_volume(fake_share)['path'])

    def test_connect_volume_failed(self):
        fake_share = fake_object.FakeManilaShare(share_proto='NFS')
        self.connector._get_access_to = mock.MagicMock()
        self.connector._get_access_to.return_value = '192.168.0.2'
        with mock.patch('fuxi.tests.unit.fake_client.FakeManilaClient'
                        '.Shares.allow',
                        side_effect=manila_exception.ClientException(500)):
            self.assertRaises(manila_exception.ClientException,
                              self.connector.connect_volume,
                              fake_share)

    def test_connect_volume_invalid_proto(self):
        fake_share = fake_object.FakeManilaShare(share_proto='invalid_proto')
        self.assertRaises(exceptions.InvalidProtocol,
                          self.connector.connect_volume,
                          fake_share)

    def test_connect_volume_invalid_access_type(self):
        fake_share = fake_object.FakeManilaShare(share_proto='NFS')
        self.connector.proto_access_type_map = {'NFS': 'invalid_type'}
        self.assertRaises(exceptions.InvalidAccessType,
                          self.connector.connect_volume,
                          fake_share)

    def test_connect_volume_invalid_access_to(self):
        fake_share = fake_object.FakeManilaShare(share_proto='GLUSTERFS')
        fake_al = [fake_object.FakeShareAccess(access_type='cert',
                                               access_to='test@local',
                                               state='active')]

        with mock.patch('fuxi.tests.unit.fake_client.FakeManilaClient.Shares'
                        '.access_list',
                        return_value=fake_al):
            self.assertRaises(exceptions.InvalidAccessTo,
                              self.connector.connect_volume,
                              fake_share)

    @mock.patch.object(mount.Mounter, 'unmount')
    def test_disconnect_volume(self, mock_unmount):
        fake_share = fake_object.FakeManilaShare(share_proto='NFS')
        self.connector._get_access_to = mock.MagicMock()
        self.connector._get_access_to.return_value = '192.168.0.2'
        self.assertIsNone(self.connector.disconnect_volume(fake_share))

    def test_get_device_path(self):
        fake_manila_share = fake_object.FakeManilaShare()
        self.assertEqual(fake_manila_share.export_location,
                         self.connector.get_device_path(fake_manila_share))

    def test_get_mountpoint(self):
        fake_manila_share = fake_object.FakeManilaShare()
        with mock.patch.object(self.connector, 'check_access_allowed',
                               return_value=False):
            self.assertEqual('',
                             self.connector.get_mountpoint(fake_manila_share))
        with mock.patch.object(self.connector, 'check_access_allowed',
                               return_value=True):
            with mock.patch.object(fake_client.FakeOSBrickConnector,
                                   'get_volume_paths',
                                   return_value=['/fuxi/data/fake-vol/nfs']):
                self.assertEqual('/fuxi/data/fake-vol',
                                 self.connector.get_mountpoint(
                                     fake_manila_share))
