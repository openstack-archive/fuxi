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
from fuxi import exceptions
from fuxi.tests import base, fake_client, fake_volume
from fuxi import utils
from fuxi.volumeprovider import cinder

from cinderclient import exceptions as cinder_exception

volume_link_dir = '/dev/disk/by-id/'
DEFAULT_VOLUME_ID = 'fake_volume_123'

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


def mock_docker_volume_for_unknown_volume(cls, docker_volume_name):
    return None, consts.UNKNOWN


def mock_docker_volume_with_state_attach_to_this(cls, docker_volume_name):
    return fake_volume.FakeCinderVolume(), consts.ATTACH_TO_THIS


def mock_docker_volume_with_state_not_attch(cls, docker_volume_name):
    return fake_volume.FakeCinderVolume(), consts.NOT_ATTACH


def mock_docker_volume_with_state_attach_to_other(cls, docker_volume_name):
    return (fake_volume.FakeCinderVolume(multiattach=False),
            consts.ATTACH_TO_OTHER)


def mock_docker_volume_with_multi_state_attach_to_other(cls,
                                                        docker_volume_name):
    return (fake_volume.FakeCinderVolume(multiattach=True),
            consts.ATTACH_TO_OTHER)


def mock_monitor_cinder_volume(cls):
    return cls.expected_obj


def test_destroy_volume(self):
    fake_cinder_volume = fake_volume.FakeCinderVolume()
    self.assertIsNone(self.connector.destroy_volume(fake_cinder_volume))


def mock_delete_failed(cls, volume_id):
    raise cinder_exception.ClientException(500)


def mock_list_failed(cls, search_opts=None):
    raise cinder_exception.ClientException(500)


def mock_device_path_for_delete(cls, volume):
    return volume.id


def mock_docker_volume_with_state_unknown(cls, docker_volume_name):
    return fake_volume.FakeCinderVolume(status='unknown'), consts.UNKNOWN


def mock_get_nonexistent_volume(*args, **kwargs):
    raise cinder_exception.ClientException(404)


def mock_docker_volume_from_volume_id(cls, docker_volume_name):
    return fake_volume.FakeCinderVolume(id=DEFAULT_VOLUME_ID), consts.UNKNOWN


def mock_docker_volume_with_state_not_match(cls, docker_volume_name):
    return fake_volume.FakeCinderVolume(status=None), None


def mock_execute(*cmd, **kwargs):
    return


class TestCinder(base.TestCase):
    volume_provider_type = 'cinder'

    def setUp(self):
        base.TestCase.setUp(self)
        self.cinderprovider = cinder.Cinder()
        self.cinderprovider.cinderclient = fake_client.FakeCinderClient()

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_for_unknown_volume)
    def test_create_with_volume_not_exist(self):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_attach_to_this)
    def test_create_with_volume_attach_to_this(self):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_not_attch)
    def test_create_with_volume_no_attach(self):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_multi_state_attach_to_other)
    def test_create_with_multiable_volume_attached_to_other(self):
        self.assertIsNone(self.cinderprovider.create('fake-vol', {}))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_attach_to_other)
    def test_create_with_volume_attached_to_other(self):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.create,
                          'fake-vol',
                          {})

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute', mock_execute)
    @mock.patch.object(FakeCinderConnector,
                       'get_device_path',
                       mock_device_path_for_delete)
    def test_delete(self):
        fd, tmpfname = tempfile.mkstemp()
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]

        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value = (
            fake_volume.FakeCinderVolume(id=tmpfname,
                                         attachments=attachments),
            consts.ATTACH_TO_THIS)
        self.cinderprovider._delete_volume = mock.MagicMock()

        self.assertTrue(self.cinderprovider.delete('fake-vol'))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_not_match)
    def test_delete_not_match_state(self):
        self.assertRaises(exceptions.NotMatchedState,
                          self.cinderprovider.delete,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute', mock_execute)
    @mock.patch.object(FakeCinderConnector,
                       'get_device_path',
                       mock_device_path_for_delete)
    @mock.patch.object(fake_client.FakeCinderClient.Volumes,
                       'delete',
                       mock_delete_failed)
    def test_delete_failed(self):
        fd, tmpfname = tempfile.mkstemp()
        attachments = [{u'server_id': u'123',
                        u'attachment_id': u'123',
                        u'attached_at': u'2016-05-20T09:19:57.000000',
                        u'host_name': utils.get_hostname(),
                        u'device': None,
                        u'id': u'123'}]

        self.cinderprovider._get_docker_volume = mock.MagicMock()
        self.cinderprovider._get_docker_volume.return_value = (
            fake_volume.FakeCinderVolume(id=tmpfname,
                                         attachments=attachments),
            consts.ATTACH_TO_THIS)

        self.assertRaises(cinder_exception.ClientException,
                          self.cinderprovider.delete,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute', mock_execute)
    @mock.patch.object(FakeCinderConnector,
                       'get_device_path',
                       mock_device_path_for_delete)
    def test_delete_timeout(self):
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
            fake_volume.FakeCinderVolume(id=tmpfname,
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
    @mock.patch.object(fake_client.FakeCinderClient.Volumes,
                       'list',
                       mock_list_failed)
    def test_list_failed(self):
        self.assertRaises(cinder_exception.ClientException,
                          self.cinderprovider.list)

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_for_unknown_volume)
    def test_path_state_unknown(self):
        self.assertRaises(exceptions.NotFound,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute', mock_execute)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_attach_to_this)
    def test_path_state_attach_to_this(self):
        self.assertEqual('', self.cinderprovider.path('fake-vol'))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_not_attch)
    def test_path_state_not_attach(self):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_attach_to_other)
    def test_path_state_attach_to_other(self):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_not_match)
    def test_path_state_not_match(self):
        self.assertRaises(exceptions.NotMatchedState,
                          self.cinderprovider.path,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(utils, 'execute', mock_execute)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_attach_to_this)
    def test_show_state_attach_to_this(self):
        self.assertEqual('', self.cinderprovider.show('fake-vol'))

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_unknown)
    def test_show_state_unknown(self):
        self.assertRaises(exceptions.NotFound,
                          self.cinderprovider.show,
                          'fake-vol')

    @mock.patch.object(cinder.Cinder, '_get_connector', mock_connector)
    @mock.patch.object(cinder.Cinder,
                       '_get_docker_volume',
                       mock_docker_volume_with_state_not_match)
    def test_show_state_not_match(self):
        self.assertRaises(exceptions.FuxiException,
                          self.cinderprovider.show,
                          'fake-vol')

    def test_mount(self):
        pass

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
            fake_volume.FakeCinderVolume(),
            consts.NOT_ATTACH)

        result = self.cinderprovider.check_exist('fake-vol')
        self.assertTrue(result)
