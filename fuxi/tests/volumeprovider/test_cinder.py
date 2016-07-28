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

import logging
from mock import mock
import os
import tempfile

from fuxi.common import config
from fuxi.common import constants as consts
from fuxi.common import mount
from fuxi.common import state_monitor
from fuxi import exceptions
from fuxi.tests import base, fake_client, fake_object
from fuxi import utils
from fuxi.volumeprovider import cinder

from cinderclient import exceptions as cinder_exception

volume_link_dir = consts.VOLUME_LINK_DIR
DEFAULT_VOLUME_ID = fake_object.DEFAULT_VOLUME_ID

CONF = config.CONF

LOG = logging.getLogger(__name__)


class FakeCinderConnector(object):
    def __init__(self):
        pass

    def connect_volume(self, volume, **connect_opts):
        return {'path': os.path.join(volume_link_dir, volume.id)}

    def disconnect_volume(self, volume, **disconnect_opts):
        pass

    def get_device_path(self, volume):
        return os.path.join(volume_link_dir, volume.id)


def mock_connector(cls):
    return FakeCinderConnector()


def mock_monitor_cinder_volume(cls):
    cls.expected_obj.status = cls.desired_state
    return cls.expected_obj


def mock_device_path_for_delete(cls, volume):
    return volume.id


class TestCinder(base.TestCase):
    volume_provider_type = 'cinder'

    def setUp(self):
        base.TestCase.setUp(self)
        self.cinderprovider = cinder.Cinder()
        self.cinderprovider.cinderclient = fake_client.FakeCinderClient()

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(None, consts.UNKNOWN))
    def test_create_with_volume_not_exist(self, mock_docker_volume):
        self.assertEqual(os.path.join(volume_link_dir, DEFAULT_VOLUME_ID),
                         self.cinderprovider.create('fake-vol', {})['path'])

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           status='unknown'), consts.UNKNOWN))
    @mock.patch.object(state_monitor.StateMonitor, 'monitor_cinder_volume',
                       mock_monitor_cinder_volume)
    def test_create_from_volume_id(self, mock_docker_volume):
        fake_volume_name = 'fake_vol'
        fake_volume_opts = {'volume_id': DEFAULT_VOLUME_ID}
        result = self.cinderprovider.create(fake_volume_name,
                                            fake_volume_opts)
        self.assertEqual(os.path.join(consts.VOLUME_LINK_DIR,
                                      DEFAULT_VOLUME_ID),
                         result['path'])

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           status='unknown'), consts.UNKNOWN))
    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.get',
                side_effect=cinder_exception.ClientException(404))
    def test_create_from_volume_id_with_volume_not_exist(self,
                                                         mocK_docker_volume,
                                                         mock_volume_get):
        fake_volume_name = 'fake_vol'
        fake_volume_opts = {'volume_id': DEFAULT_VOLUME_ID}
        self.assertRaises(cinder_exception.ClientException,
                          self.cinderprovider.create,
                          fake_volume_name,
                          fake_volume_opts)

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           status='unknown'), consts.UNKNOWN))
    def test_create_from_volume_id_with_unexpected_status_1(
            self, mock_docker_volume):
        fake_volume_name = 'fake_vol'
        fake_volume_args = {'volume_id': DEFAULT_VOLUME_ID,
                            'status': 'attaching'}
        fake_cinder_volume = fake_object.FakeCinderVolume(**fake_volume_args)
        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value \
            = (fake_cinder_volume,
               consts.UNKNOWN)
        self.cinderprovider.cinderclient.volumes.get = mock.MagicMock()
        self.cinderprovider.cinderclient.volumes.get.return_value = \
            fake_cinder_volume
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.create,
                          fake_volume_name,
                          {'volume_id': DEFAULT_VOLUME_ID})

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    def test_create_from_volume_id_with_unexpected_status_2(self):
        fake_server_id = 'fake_server_123'
        fake_host_name = 'attached_to_other'
        fake_volume_name = 'fake_vol'
        fake_volume_args = {'volume_id': DEFAULT_VOLUME_ID,
                            'status': 'in-use',
                            'multiattach': False,
                            'attachments': [{'server_id': fake_server_id,
                                             'host_name': fake_host_name}]}
        fake_cinder_volume = fake_object.FakeCinderVolume(**fake_volume_args)
        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value \
            = (fake_cinder_volume,
               consts.UNKNOWN)
        self.cinderprovider.cinderclient.volumes.get = mock.MagicMock()
        self.cinderprovider.cinderclient.volumes.get.return_value = \
            fake_cinder_volume
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.create,
                          fake_volume_name,
                          {'volume_id': DEFAULT_VOLUME_ID})

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    def test_create_with_volume_attach_to_this(self):
        fake_server_id = 'fake_server_123'
        fake_host_name = 'attached_to_this'
        fake_volume_args = {'id': DEFAULT_VOLUME_ID,
                            'status': 'in-use',
                            'attachments': [{'server_id': fake_server_id,
                                             'host_name': fake_host_name}]
                            }
        fake_cinder_volume = fake_object.FakeCinderVolume(**fake_volume_args)
        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value \
            = (fake_cinder_volume,
               consts.ATTACH_TO_THIS)
        self.cinderprovider.cinderclient.volumes.get = mock.MagicMock()
        self.cinderprovider.cinderclient.volumes.get.return_value = \
            fake_cinder_volume
        fake_result = self.cinderprovider.create('fake-vol', {})
        self.assertEqual(os.path.join(volume_link_dir, DEFAULT_VOLUME_ID),
                         fake_result['path'])

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    def test_create_with_volume_no_attach(self):
        fake_cinder_volume = fake_object.FakeCinderVolume()
        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value \
            = (fake_cinder_volume,
               consts.NOT_ATTACH)
        fake_result = self.cinderprovider.create('fake-vol', {})
        self.assertEqual(os.path.join(volume_link_dir, DEFAULT_VOLUME_ID),
                         fake_result['path'])

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           multiattach=True), consts.ATTACH_TO_OTHER))
    def test_create_with_multiable_vol_attached_to_other(self,
                                                         mock_docker_volume):
        self.assertEqual(os.path.join(volume_link_dir,
                                      fake_object.DEFAULT_VOLUME_ID),
                         self.cinderprovider.create('fake-vol', {})['path'])

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           multiattach=False), consts.ATTACH_TO_OTHER))
    def test_create_with_volume_attached_to_other(self, mock_docker_volume):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.create,
                          'fake-vol',
                          {})

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(FakeCinderConnector,
                       'get_device_path',
                       mock_device_path_for_delete)
    def test_delete(self, mock_execute):
        fd, tmpfname = tempfile.mkstemp()
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]

        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value = (
            fake_object.FakeCinderVolume(id=tmpfname,
                                         attachments=attachments),
            consts.ATTACH_TO_THIS)
        self.cinderprovider._delete_volume = mock.MagicMock()

        self.assertTrue(self.cinderprovider.delete('fake-vol'))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(status=None),
                                     None))
    def test_delete_not_match_state(self, mock_docker_volume):
        self.assertRaises(exceptions.NotMatchedState,
                          self.cinderprovider.delete,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(FakeCinderConnector,
                       'get_device_path',
                       mock_device_path_for_delete)
    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.delete',
                side_effect=cinder_exception.ClientException(500))
    def test_delete_failed(self, mock_execute, mock_delete):
        fd, tmpfname = tempfile.mkstemp()
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]

        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value = (
            fake_object.FakeCinderVolume(id=tmpfname,
                                         attachments=attachments),
            consts.ATTACH_TO_THIS)

        self.assertRaises(cinder_exception.ClientException,
                          self.cinderprovider.delete,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(FakeCinderConnector,
                       'get_device_path',
                       mock_device_path_for_delete)
    def test_delete_timeout(self, mock_execute):
        consts.DESTROY_VOLUME_TIMEOUT = 4
        fd, tmpfname = tempfile.mkstemp()
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]

        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value = (
            fake_object.FakeCinderVolume(id=tmpfname,
                                         attachments=attachments),
            consts.ATTACH_TO_THIS)

        self.assertRaises(exceptions.TimeoutException,
                          self.cinderprovider.delete,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    def test_list(self):
        docker_volumes = self.cinderprovider.list()
        self.assertEqual(docker_volumes, [])

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.list',
                side_effect=cinder_exception.ClientException(500))
    def test_list_failed(self, mock_list):
        self.assertRaises(cinder_exception.ClientException,
                          self.cinderprovider.list)

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(),
                                     consts.ATTACH_TO_THIS))
    def test_show_state_attach_to_this(self, mock_execute, mock_docker_volume):
        self.assertEqual({'Name': 'fake-vol', 'Mountpoint': ''},
                         self.cinderprovider.show('fake-vol'))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           status='unknown'), consts.UNKNOWN))
    def test_show_state_unknown(self, mock_docker_volume):
        self.assertRaises(exceptions.NotFound,
                          self.cinderprovider.show,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(status=None),
                                     None))
    def test_show_state_not_match(self, mock_docker_volume):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.show,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           name='fake-vol',
                           status='in-use'), consts.ATTACH_TO_THIS))
    @mock.patch.object(cinder.Cinder, '_create_mountpoint')
    @mock.patch.object(mount, 'do_mount')
    def test_mount(self, mock_docker_volume, mock_create_mp, mock_do_mount):
        fd, fake_devpath = tempfile.mkstemp()
        fake_link_path = fake_devpath
        fake_mountpoint = 'fake-mount-point/'
        with mock.patch.object(FakeCinderConnector, 'get_device_path',
                               return_value=fake_link_path):
            with mock.patch.object(cinder.Cinder, '_get_mountpoint',
                                   return_value=fake_mountpoint):
                self.assertEqual(fake_mountpoint,
                                 self.cinderprovider.mount('fake-vol'))

    def test_unmount(self):
        self.assertIsNone(self.cinderprovider.unmount('fake-vol'))

    def test_check_exists(self):
        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value = (
            None,
            consts.UNKNOWN)

        result = self.cinderprovider.check_exist('fake-vol')
        self.assertFalse(result)

        self.cinderprovider._get_docker_volume.return_value = (
            fake_object.FakeCinderVolume(),
            consts.NOT_ATTACH)

        result = self.cinderprovider.check_exist('fake-vol')
        self.assertTrue(result)
