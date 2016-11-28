# -*- coding: utf-8 -*-

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

"""
test_fuxi
----------------------------------

Tests for `fuxi` module.
"""
import collections
import mock
import unittest

from fuxi import app
from fuxi.common import config
from fuxi.controllers import volume_providers_conf
from fuxi import exceptions
from fuxi.tests.unit import base

from oslo_serialization import jsonutils


def fake_mountpoint(name):
    volume_dir = config.CONF.volume_dir.rstrip('/')
    return ''.join((volume_dir, name))


def fake_volume(name):
    volume_dir = config.CONF.volume_dir.rstrip('/')
    return {'Name': name, 'Mountpoint': ''.join((volume_dir, name))}


class FakeProvider(object):
    def __init__(self, volume_provider_type):
        self.volume_provider_type = volume_provider_type

    def create(self, docker_volume_name, volume_opts):
        pass

    def delete(self, docker_volume_name):
        pass

    def list(self):
        pass

    def path(self, docker_volume_name):
        pass

    def show(self, docker_volume_name):
        pass

    def mount(self, docker_volume_name):
        pass

    def unmount(self, docker_volume_name):
        pass

    def check_exist(self, docker_volume_name):
        return False


class TestFuxi(base.TestCase):
    def setUp(self):
        super(TestFuxi, self).setUp()
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        self.app = app.test_client()

    def volume_providers_setup(self, volume_provider_types):
        if not volume_provider_types:
            raise Exception

        app.volume_providers = collections.OrderedDict()
        for vpt in volume_provider_types:
            if vpt in volume_providers_conf:
                app.volume_providers[vpt] = FakeProvider(vpt)

    def test_plugin_activate(self):
        response = self.app.post('/Plugin.Activate')
        fake_response = {
            u'Implements': [u'VolumeDriver']
        }
        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_create(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {
            u'Name': u'test-vol',
            u'Opts': {u'size': u'1'},
        }
        for provider in app.volume_providers.values():
            provider.check_exist = mock.MagicMock()
            provider.check_exist.return_value = False
            provider.create = mock.MagicMock()

        response = self.app.post('/VolumeDriver.Create',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u''
        }

        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_create_without_name(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {u'Opts': {}}
        response = self.app.post('VolumeDriver.Create',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        self.assertEqual(500, response.status_code)
        self.assertIsNotNone(jsonutils.loads(response.data))

    def test_volumedriver_create_with_invalid_opts(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {u'Name': u'test-vol', u'Opts': u'invalid'}
        response = self.app.post('VolumeDriver.Create',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        self.assertEqual(500, response.status_code)
        self.assertIsNotNone(jsonutils.loads(response.data))

    def test_volumedriver_create_invalid_volume_provider(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {
            u'Name': u'test-vol',
            u'Opts': {u'size': u'1',
                      u'volume_provider': u'provider'}}
        for provider in app.volume_providers.values():
            provider.check_exist = mock.MagicMock()
            provider.check_exist.return_value = False
            provider.create = mock.MagicMock()

        response = self.app.post('VolumeDriver.Create',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u''
        }
        self.assertEqual(200, response.status_code)
        self.assertNotEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_remove(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {
            u'Name': u'test-vol'
        }
        for provider in app.volume_providers.values():
            provider.delete = mock.MagicMock()
            provider.delete.return_value = True

        response = self.app.post('/VolumeDriver.Remove',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u''
        }
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_remove_with_volume_not_exist(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {
            u'Name': u'test-vol',
        }
        for provider in app.volume_providers.values():
            provider.delete = mock.MagicMock()
            provider.delete.return_value = False

        response = self.app.post('/VolumeDriver.Remove',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u''
        }
        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_mount(self):
        self.volume_providers_setup(['cinder'])
        fake_name = u'test-vol'
        fake_request = {
            u'Name': fake_name
        }

        for provider in app.volume_providers.values():
            provider.check_exist = mock.MagicMock()
            provider.check_exist.return_value = True
            provider.mount = mock.MagicMock()
            provider.mount.return_value = fake_mountpoint(fake_name)

        response = self.app.post('/VolumeDriver.Mount',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Mountpoint': fake_mountpoint(fake_name),
            u'Err': u''
        }
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_mount_with_volume_not_exist(self):
        self.volume_providers_setup(['cinder'])
        fake_name = u'test-vol'
        fake_request = {
            u'Name': fake_name,
        }
        for provider in app.volume_providers.values():
            provider.check_exit = mock.MagicMock()
            provider.check_exit.return_value = False
        response = self.app.post('/VolumeDriver.Mount',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Mountpoint': fake_mountpoint(fake_name),
            u'Err': u''
        }
        self.assertEqual(200, response.status_code)
        self.assertNotEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_path(self):
        self.volume_providers_setup(['cinder'])
        fake_name = u'test-vol'
        fake_request = {
            u'Name': fake_name
        }
        for provider in app.volume_providers.values():
            provider.show = mock.MagicMock()
            provider.show.return_value = fake_volume(fake_name)

        response = self.app.post('/VolumeDriver.Path',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Mountpoint': fake_mountpoint(fake_name),
            u'Err': u''
        }
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_path_with_volume_not_exist(self):
        self.volume_providers_setup(['cinder'])
        fake_docker_volume_name = u'test-vol'
        fake_request = {
            u'Name': fake_docker_volume_name
        }
        for provider in app.volume_providers.values():
            provider.show = mock.MagicMock(side_effect=exceptions.NotFound)

        response = self.app.post('/VolumeDriver.Path',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u'Mountpoint Not Found'
        }
        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_unmount(self):
        self.volume_providers_setup(['cinder'])
        fake_request = {
            u'Name': u'test-vol'
        }
        response = self.app.post('/VolumeDriver.Unmount',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u''
        }
        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_get(self):
        self.volume_providers_setup(['cinder'])
        fake_name = u'test-vol'
        fake_request = {
            u'Name': fake_name
        }
        for provider in app.volume_providers.values():
            provider.show = mock.MagicMock()
            provider.show.return_value = fake_volume(fake_name)

        response = self.app.post('/VolumeDriver.Get',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Volume': {u'Name': fake_name,
                        u'Mountpoint': fake_mountpoint(fake_name)},
            u'Err': u''
        }
        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_get_with_volume_not_exist(self):
        self.volume_providers_setup(['cinder'])
        fake_docker_volume_name = u'test-vol'
        fake_request = {
            u'Name': fake_docker_volume_name
        }
        for provider in app.volume_providers.values():
            provider.show = mock.MagicMock(side_effect=exceptions.NotFound())

        response = self.app.post('/VolumeDriver.Get',
                                 content_type='application/json',
                                 data=jsonutils.dumps(fake_request))
        fake_response = {
            u'Err': u'Volume Not Found'
        }
        self.assertEqual(200, response.status_code)
        self.assertEqual(fake_response, jsonutils.loads(response.data))

    def test_volumedriver_list(self):
        self.volume_providers_setup(['cinder'])
        for provider in app.volume_providers.values():
            provider.list = mock.MagicMock()
            provider.list.return_value = []

        response = self.app.post('/VolumeDriver.List',
                                 content_type='application/json')

        fake_response = {
            u'Volumes': [],
            u'Err': u''
        }
        self.assertEqual(fake_response, jsonutils.loads(response.data))

if __name__ == '__main__':
    unittest.main()
