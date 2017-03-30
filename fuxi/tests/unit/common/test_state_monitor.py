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

from cinderclient import exceptions as cinder_exception
from manilaclient.common.apiclient import exceptions as manila_exception

from fuxi.common import state_monitor
from fuxi import exceptions
from fuxi.tests.unit import base, fake_client, fake_object


class TestStateMonitor(base.TestCase):
    def test_monitor_cinder_volume(self):
        fake_cinder_client = fake_client.FakeCinderClient()
        fake_cinder_volume = fake_object.FakeCinderVolume(status='available')
        fake_desired_state = 'in-use'
        fake_transient_states = ('in-use',)
        fake_time_limit = 0
        fake_state_monitor = state_monitor.StateMonitor(fake_cinder_client,
                                                        fake_cinder_volume,
                                                        fake_desired_state,
                                                        fake_transient_states,
                                                        fake_time_limit)

        fake_desired_volume = fake_object.FakeCinderVolume(status='in-use')
        with mock.patch.object(fake_client.FakeCinderClient.Volumes, 'get',
                               return_value=fake_desired_volume):
            self.assertEqual(fake_desired_volume,
                             fake_state_monitor.monitor_cinder_volume())

    def test_monitor_cinder_volume_get_failed(self):
        fake_cinder_client = fake_client.FakeCinderClient()
        fake_cinder_volume = fake_object.FakeCinderVolume(status='available')

        with mock.patch('fuxi.tests.unit.fake_client.FakeCinderClient.Volumes'
                        '.get',
                        side_effect=cinder_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_cinder_client,
                                                            fake_cinder_volume,
                                                            None, None, -1)
            self.assertRaises(exceptions.TimeoutException,
                              fake_state_monitor.monitor_cinder_volume)

        with mock.patch('fuxi.tests.unit.fake_client.FakeCinderClient.Volumes'
                        '.get',
                        side_effect=cinder_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_cinder_client,
                                                            fake_cinder_volume,
                                                            None, None)
            self.assertRaises(cinder_exception.ClientException,
                              fake_state_monitor.monitor_cinder_volume)

    def test_monitor_cinder_volume_unexpected_state(self):
        fake_cinder_client = fake_client.FakeCinderClient()
        fake_cinder_volume = fake_object.FakeCinderVolume(status='available')
        fake_desired_state = 'in-use'
        fake_transient_states = ('in-use',)
        fake_time_limit = 0

        fake_state_monitor = state_monitor.StateMonitor(fake_cinder_client,
                                                        fake_cinder_volume,
                                                        fake_desired_state,
                                                        fake_transient_states,
                                                        fake_time_limit)
        fake_desired_volume = fake_object.FakeCinderVolume(status='attaching')

        with mock.patch.object(fake_client.FakeCinderClient.Volumes, 'get',
                               return_value=fake_desired_volume):
            self.assertRaises(exceptions.UnexpectedStateException,
                              fake_state_monitor.monitor_cinder_volume)

    def test_monitor_manila_share(self):
        fake_manila_client = fake_client.FakeManilaClient()
        fake_manila_share = fake_object.FakeManilaShare(status='creating')
        fake_desired_state = 'available'
        fake_transient_states = ('creating',)
        fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                        fake_manila_share,
                                                        fake_desired_state,
                                                        fake_transient_states,
                                                        0)

        fake_desired_share = fake_object.FakeManilaShare(status='available')
        with mock.patch.object(fake_client.FakeManilaClient.Shares, 'get',
                               return_value=fake_desired_share):
            self.assertEqual(fake_desired_share,
                             fake_state_monitor.monitor_manila_share())

    def test_monitor_manila_share_get_failed(self):
        fake_manila_client = fake_client.FakeManilaClient()
        fake_manila_share = fake_object.FakeManilaShare(status='creating')

        with mock.patch('fuxi.tests.unit.fake_client'
                        '.FakeManilaClient.Shares.get',
                        side_effect=manila_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                            fake_manila_share,
                                                            None, None, -1)
            self.assertRaises(exceptions.TimeoutException,
                              fake_state_monitor.monitor_manila_share)

        with mock.patch('fuxi.tests.unit.fake_client'
                        '.FakeManilaClient.Shares.get',
                        side_effect=manila_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                            fake_manila_share,
                                                            None, None)
            self.assertRaises(manila_exception.ClientException,
                              fake_state_monitor.monitor_manila_share)

    def test_monitor_manila_share_unexpected_state(self):
        fake_manila_client = fake_client.FakeManilaClient()
        fake_manila_share = fake_object.FakeManilaShare(status='creating')

        fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                        fake_manila_share,
                                                        'available',
                                                        ('creating',),
                                                        0)
        fake_desired_share = fake_object.FakeCinderVolume(status='unknown')

        with mock.patch.object(fake_client.FakeManilaClient.Shares, 'get',
                               return_value=fake_desired_share):
            self.assertRaises(exceptions.UnexpectedStateException,
                              fake_state_monitor.monitor_manila_share)

    def test_monitor_share_access(self):
        fake_manila_client = fake_client.FakeManilaClient()
        fake_manila_share = fake_object.FakeManilaShare()
        fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                        fake_manila_share,
                                                        'active',
                                                        ('new',),
                                                        0)

        fake_desired_sl = [fake_object.FakeShareAccess(
            access_type='ip', access_to='192.168.0.1', state='active')]
        with mock.patch.object(fake_client.FakeManilaClient.Shares,
                               'access_list',
                               return_value=fake_desired_sl):
            self.assertEqual(fake_manila_share,
                             fake_state_monitor.monitor_share_access(
                                 'ip', '192.168.0.1'))

    def test_monitor_share_access_list_failed(self):
        fake_manila_client = fake_client.FakeManilaClient()
        fake_manila_share = fake_object.FakeManilaShare()
        with mock.patch('fuxi.tests.unit.fake_client.FakeManilaClient.Shares'
                        '.access_list',
                        side_effect=manila_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                            fake_manila_share,
                                                            None, None, -1)
            self.assertRaises(exceptions.TimeoutException,
                              fake_state_monitor.monitor_share_access,
                              'ip', '192.168.0.1')

        with mock.patch('fuxi.tests.unit.fake_client.FakeManilaClient.Shares'
                        '.access_list',
                        side_effect=manila_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                            fake_manila_share,
                                                            None, None)
            self.assertRaises(manila_exception.ClientException,
                              fake_state_monitor.monitor_share_access,
                              'ip', '192.168.0.1')

    def test_monitor_share_access_unexpected_state(self):
        fake_manila_client = fake_client.FakeManilaClient()
        fake_manila_share = fake_object.FakeManilaShare()

        fake_state_monitor = state_monitor.StateMonitor(fake_manila_client,
                                                        fake_manila_share,
                                                        'active',
                                                        ('new',),
                                                        0)
        fake_desired_sl = [fake_object.FakeShareAccess(
            access_type='ip', access_to='192.168.0.1', state='unknown')]
        with mock.patch.object(fake_client.FakeManilaClient.Shares,
                               'access_list', return_value=fake_desired_sl):
            self.assertRaises(exceptions.UnexpectedStateException,
                              fake_state_monitor.monitor_share_access,
                              'ip', '192.168.0.1')
