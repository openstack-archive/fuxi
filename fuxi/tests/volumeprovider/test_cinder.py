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
import tempfile

from fuxi.common import config
from fuxi.common import constants as consts
from fuxi.common import mount
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
        pass

    def disconnect_volume(self, volume, **disconnect_opts):
        pass

    def get_device_path(self, volume):
        return volume_link_dir + volume.id


def mock_connector(cls):
    return FakeCinderConnector()


def mock_monitor_cinder_volume(cls):
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
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(),
                                     consts.ATTACH_TO_THIS))
    def test_create_with_volume_attach_to_this(self, mock_docker_volume):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(),
                                     consts.NOT_ATTACH))
    def test_create_with_volume_no_attach(self, mock_docker_volume):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           multiattach=True), consts.ATTACH_TO_OTHER))
    def test_create_with_multiable_vol_attached_to_other(self,
                                                         mock_docker_volume):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

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
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(None, consts.UNKNOWN))
    def test_path_state_unknown(self, mock_docker_volume):
        self.assertRaises(exceptions.NotFound,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(),
                                     consts.ATTACH_TO_THIS))
    def test_path_state_attach_to_this(self, mock_execute, mock_docker_volume):
        self.assertEqual('', self.cinderprovider.path('fake-vol'))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(),
                                     consts.NOT_ATTACH))
    def test_path_state_not_attach(self, mock_docker_volume):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(
                           multiattach=False), consts.ATTACH_TO_OTHER))
    def test_path_state_attach_to_other(self, mock_docker_volume):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(status=None),
                                     None))
    def test_path_state_not_match(self, mock_docker_volume):
        self.assertRaises(exceptions.NotMatchedState,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute')
    @mock.patch.object(cinder.Cinder, '_get_docker_volume',
                       return_value=(fake_object.FakeCinderVolume(),
                                     consts.ATTACH_TO_THIS))
    def test_show_state_attach_to_this(self, mock_execute, mock_docker_volume):
        self.assertEqual('', self.cinderprovider.show('fake-vol'))

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
    @mock.patch.object(mount, 'do_mount')
    def test_mount(self, mock_docker_volume, mock_do_mount):
        out, err = utils.execute('losetup', '-f', run_as_root=True)
        utils.execute('dd',
                      'if=/dev/zero', 'of=loop.img',
                      'bs=1M', 'count=1',
                      run_as_root=True)
        utils.execute('losetup', '-f', 'loop.img', run_as_root=True)
        link_path = '/tmp/fake-path-123'
        fake_mountpoint = '/tmp/fake-mount-point/'
        utils.execute('ln', '-s', out.strip(), link_path)
        with mock.patch.object(FakeCinderConnector, 'get_device_path',
                               return_value=link_path):
            with mock.patch.object(cinder.Cinder, '_get_mountpoint',
                                   return_value=fake_mountpoint):
                self.assertEqual(fake_mountpoint,
                                 self.cinderprovider.mount('fake-vol'))
                utils.execute('rm', link_path, run_as_root=True)
                utils.execute('losetup', '-d', out.strip())
                utils.execute('rmdir', fake_mountpoint, run_as_root=True)

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
