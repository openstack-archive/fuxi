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

import glob

from oslo_log import log as logging
from oslo_utils import units

from fuxi import exceptions
from fuxi.i18n import _LE

LOG = logging.getLogger(__name__)


class BlockerDeviceManager(object):
    def device_scan(self):
        return glob.glob('/sys/block/*')

    def get_device_size(self, device):
        try:
            nr_sectors = open(device + '/size').read().rstrip('\n')
            sect_size = open(device + '/queue/hw_sector_size')\
                .read().rstrip('\n')
            return (float(nr_sectors) * float(sect_size)) / units.Gi
        except IOError as e:
            LOG.error(_LE("Failed to read device size. {0}").format(e))
            raise exceptions.FuxiException(e.message)
