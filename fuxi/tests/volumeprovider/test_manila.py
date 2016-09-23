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

from manilaclient.openstack.common.apiclient import exceptions \
    as manila_exception

from fuxi.common import constants as consts
from fuxi.common import mount
from fuxi.common import state_monitor
from fuxi import exceptions
from fuxi.tests import base, fake_client, fake_object
from fuxi import utils
from fuxi.volumeprovider import manila


class FakeManilaConnector(object):
    def __init__(self):
        pass

    def connect_volume(self, share, **connect_opts):
        return {'path': share.export_location}

    def disconnect_volume(self, share, **disconnect_opts):
        pass

    def get_device_path(self, share):
        return share.export_location

    def get_mountpoint(self, share):
        return share.name


def mock_monitor_manila_share(cls):
    cls.expected_obj.status = cls.desired_state
    return cls.expected_obj


class TestManila(base.TestCase):
    def setUp(self):
        super(TestManila, self).setUp()
        self._set_up_provider()

    @mock.patch.object(utils, 'get_manilaclient',
                       return_value=fake_client.FakeManilaClient())
    def _set_up_provider(self, mock_client):
        self.provider = manila.Manila()
        self.provider.manilaclient = fake_client.FakeManilaClient()
        self.provider.connector = FakeManilaConnector()

    def test_create_exist(self):
        fake_share = fake_object.FakeManilaShare(
            name='fake-vol', id='fake-id',
            export_location='fake-el')

        for status in [consts.NOT_ATTACH, consts.ATTACH_TO_THIS]:
            with mock.patch.object(manila.Manila, '_get_docker_volume',
                                   return_value=(fake_share, status)):
                self.assertEqual('fake-el',
                                 self.provider.create('fake-vol', {})['path'])

    @mock.patch('fuxi.volumeprovider.manila.Manila._get_docker_volume',
                side_effect=exceptions.NotFound())
    def test_create_from_id(self, mock_docker_volume):
        fake_vol_opts = {'volume_id': 'fake-id'}
        fake_share = fake_object.FakeManilaShare(
            name='fake-vol', id='fake-id',
            export_location='fake-el', status='available', metadata={})
        with mock.patch.object(fake_client.FakeManilaClient.Shares, 'get',
                               return_value=fake_share):
            self.assertEqual('fake-el',
                             self.provider.create('fake-vol',
                                                  fake_vol_opts)['path'])

    @mock.patch('fuxi.volumeprovider.manila.Manila._get_docker_volume',
                side_effect=exceptions.NotFound())
    def test_create_not_exist(self, mock_docker_volume):
        fake_vol_opts = {'share_network': 'fake-share-network'}
        fake_share = fake_object.FakeManilaShare(
            name='fake-vol', id='fake-id',
            export_location='fake-el', status='creating')
        with mock.patch.object(fake_client.FakeManilaClient.Shares, 'create',
                               return_value=fake_share):
            fake_share.status = 'available'
            with mock.patch.object(state_monitor.StateMonitor,
                                   'monitor_manila_share',
                                   return_value=fake_share):
                self.assertEqual('fake-el',
                                 self.provider.create('fake-vol',
                                                      fake_vol_opts)['path'])

    @mock.patch.object(utils, 'execute')
    @mock.patch.object(mount.Mounter, 'get_mps_by_device',
                       return_value=[])
    def test_delete(self, mock_execute, mock_mps):
        fake_share = fake_object.FakeManilaShare(
            name='fake-vol', id='fake-id',
            export_location='fake-el')

        with mock.patch.object(manila.Manila, '_get_docker_volume',
                               return_value=(fake_share,
                                             consts.ATTACH_TO_THIS)):
            with mock.patch.object(manila.Manila, '_delete_share'):
                self.assertTrue(self.provider.delete('fake-vol'))

    def test_mount(self):
        fake_share = fake_object.FakeManilaShare(
            name='fake-vol', id='fake-id',
            export_location='fake-el', share_proto='nfs')

        with mock.patch.object(manila.Manila, '_get_docker_volume',
                               return_value=(fake_share,
                                             consts.ATTACH_TO_THIS)):
            self.assertEqual('fake-vol',
                             self.provider.mount('fake-vol'))

    def test_unmount(self):
        self.assertIsNone(self.provider.unmount('fake-vol'))

    def test_show(self):
        fake_vol = fake_object.DEFAULT_VOLUME_NAME
        with mock.patch.object(manila.Manila, '_get_docker_volume',
                               return_value=(fake_object.FakeManilaShare(),
                                             consts.ATTACH_TO_THIS)):
            self.assertEqual({'Name': fake_vol,
                              'Mountpoint': fake_vol},
                             self.provider.show(fake_vol))

    @mock.patch('fuxi.tests.fake_client.FakeManilaClient.Shares.list',
                side_effect=manila_exception.ClientException(500))
    def test_show_list_failed(self, mock_list):
        self.assertRaises(manila_exception.ClientException,
                          self.provider.show, 'fake-vol')

    @mock.patch.object(fake_client.FakeManilaClient.Shares, 'list',
                       return_value=[])
    def test_show_no_share(self, mock_list):
        self.assertRaises(exceptions.NotFound, self.provider.show, 'fake-vol')

    @mock.patch.object(fake_client.FakeManilaClient.Shares, 'list',
                       return_value=[fake_object.FakeManilaShare(id='1'),
                                     fake_object.FakeManilaShare(id='2')])
    def test_show_too_many_shares(self, mock_list):
        self.assertRaises(exceptions.TooManyResources,
                          self.provider.show, 'fake-vol')

    @mock.patch.object(manila.Manila, '_get_docker_volume',
                       return_value=(fake_object.FakeManilaShare(),
                                     consts.NOT_ATTACH))
    def test_show_not_attach(self, mock_docker_volume):
        fake_vol = fake_object.DEFAULT_VOLUME_NAME
        self.assertEqual({'Name': fake_vol, 'Mountpoint': fake_vol},
                         self.provider.show(fake_vol))

    @mock.patch.object(manila.Manila, '_get_docker_volume',
                       return_value=(fake_object.FakeManilaShare(),
                                     consts.ATTACH_TO_THIS))
    def test_show_not_mount(self, mock_dokcer_volume):
        fake_vol = fake_object.DEFAULT_VOLUME_NAME
        self.assertEqual({'Name': fake_vol,
                          'Mountpoint': fake_vol},
                         self.provider.show(fake_vol))

    def test_list(self):
        share_dict = [
            {'id': 'fake-id1', 'name': 'fake-name1',
             'export_location': 'fake-el1'},
            {'id': 'fake-id2', 'name': 'fake-name2',
             'export_location': 'fake-el2'}
        ]
        fake_shares = [fake_object.FakeManilaShare(**s) for s in share_dict]
        fake_volumes = [{'Name': 'fake-name1', 'Mountpoint': 'fake-name1'},
                        {'Name': 'fake-name2', 'Mountpoint': 'fake-name2'}]
        with mock.patch.object(fake_client.FakeManilaClient.Shares, 'list',
                               return_value=fake_shares):
            with mock.patch.object(mount.Mounter, 'get_mps_by_device',
                                   return_value=[]):
                self.assertEqual(fake_volumes, self.provider.list())

    def test_list_failed(self):
        with mock.patch('fuxi.tests.fake_client.FakeManilaClient.Shares.list',
                        side_effect=manila_exception.ClientException):
            self.assertRaises(manila_exception.ClientException,
                              self.provider.list)

    def test_check_exist(self):
        with mock.patch('fuxi.volumeprovider.manila.Manila._get_docker_volume',
                        side_effect=exceptions.NotFound()):
            self.assertFalse(self.provider.check_exist('fake-vol'))

        with mock.patch.object(manila.Manila, '_get_docker_volume',
                               return_value=(fake_object.FakeManilaShare(),
                                             consts.ATTACH_TO_THIS)):
            self.assertTrue(self.provider.check_exist('fake-vol'))
