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

import time

from fuxi.common import constants
from fuxi import exceptions
from fuxi.i18n import _LE

from cinderclient import exceptions as cinder_exception

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class StateMonitor(object):
    """Monitor the status of Volume.

    Because of some volume operation is asynchronous, such as creating Cinder
    volume, this volume could be used for next stop util reached an desired
    state.
    """
    def __init__(self, client, expected_obj,
                 desired_state,
                 transient_states=(),
                 time_limit=constants.MONITOR_STATE_TIMEOUT,
                 time_delay=1):
        self.client = client
        self.expected_obj = expected_obj
        self.desired_state = desired_state
        self.transient_states = transient_states
        self.time_limit = time_limit
        self.start_time = time.time()
        self.time_delay = time_delay

    def _reached_desired_state(self, current_state):
        if current_state == self.desired_state:
            return True
        elif current_state in self.transient_states:
            idx = self.transient_states.index(current_state)
            if idx > 0:
                self.transient_states = self.transient_states[idx:]
            return False
        else:
            msg = _LE("Unexpected state while waiting for volume. "
                      "Expected Volume: {0}, "
                      "Expected State: {1}, "
                      "Reached State: {2}").format(self.expected_obj,
                                                   self.desired_state,
                                                   current_state)
            LOG.error(msg)
            raise exceptions.UnexpectedStateException(msg)

    def monitor_cinder_volume(self):
        while True:
            try:
                volume = self.client.volumes.get(self.expected_obj.id)
            except cinder_exception.ClientException:
                elapsed_time = time.time() - self.start_time
                if elapsed_time > self.time_limit:
                    msg = _LE("Timed out while waiting for volume. "
                              "Expected Volume: {0}, "
                              "Expected State: {1}, "
                              "Elapsed Time: {2}").format(self.expected_obj,
                                                          self.desired_state,
                                                          elapsed_time)
                    LOG.error(msg)
                    raise exceptions.TimeoutException(msg)
                raise

            if self._reached_desired_state(volume.status):
                return volume

            time.sleep(self.time_delay)
