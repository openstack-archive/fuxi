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

from fuxi.common import state_monitor
from fuxi import exceptions
from fuxi.tests import base, fake_client, fake_object


class TestStateMonitor(base.TestCase):
    def setUp(self):
        super(TestStateMonitor, self).setUp()

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

        with mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.get',
                        side_effect=cinder_exception.ClientException(404)):
            fake_state_monitor = state_monitor.StateMonitor(fake_cinder_client,
                                                            fake_cinder_volume,
                                                            None, None, -1)
            self.assertRaises(exceptions.TimeoutException,
                              fake_state_monitor.monitor_cinder_volume)

        with mock.patch('fuxi.tests.fake_client.FakeCinderClient.Volumes.get',
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
