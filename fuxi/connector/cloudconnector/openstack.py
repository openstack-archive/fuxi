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

import os

from cinderclient import exceptions as cinder_exception
from novaclient import exceptions as nova_exception
from oslo_log import log as logging

from fuxi.common import config
from fuxi.common import state_monitor
from fuxi.connector import connector
from fuxi.i18n import _LI, _LW, _LE
from fuxi import utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class CinderConnector(connector.Connector):
    def __init__(self, cinderclient=None, *args, **kwargs):
        super(CinderConnector, self).__init__()
        if not cinderclient:
            cinderclient = utils.get_cinderclient()
        self.cinderclient = cinderclient
        self.novaclient = utils.get_novaclient()

    def connect_volume(self, volume, **connect_opts):
        try:
            server_id = connect_opts.get('server_id', None)
            if not server_id:
                server_id = utils.get_instance_uuid()

            LOG.info(_LI("Start to connect to volume %s"), volume)
            nova_volume = self.novaclient.volumes.create_server_volume(
                server_id=server_id,
                volume_id=volume.id,
                device=None)

            volume_monitor = state_monitor.StateMonitor(
                self.cinderclient,
                nova_volume,
                'in-use',
                ('available', 'attaching',))
            volume_monitor.monitor_cinder_volume()
        except nova_exception.ClientException as ex:
            LOG.error(_LE("Attaching volume %(vol)s to server %(s)s "
                          "failed. Error: %(err)s"),
                      {'vol': volume.id, 's': server_id, 'err': ex})
            raise

        utils.execute('udevadm', 'trigger', run_as_root=True)

        dev_path = self.get_device_path(volume)
        if not dev_path:
            LOG.warning(_LW("Could not find matched device for volume %s"),
                        volume.id)
        return {'path', dev_path}

    def disconnect_volume(self, volume, **disconnect_opts):
        try:
            volume = self.cinderclient.volumes.get(volume.id)
        except cinder_exception.ClientException as e:
            LOG.error(_LE("Get Volume %s from Cinder failed"), volume.id)
            raise

        try:
            self.novaclient.volumes.delete_server_volume(
                utils.get_instance_uuid(),
                volume.id)
        except nova_exception.ClientException as e:
            LOG.error(_LE("Detaching volume %(vol)s failed. Err: %(err)s"),
                      {'vol': volume.id, 'err': e})
            raise

        volume_monitor = state_monitor.StateMonitor(self.cinderclient,
                                                    volume,
                                                    'available',
                                                    ('in-use', 'detaching',))
        return volume_monitor.monitor_cinder_volume()

    def get_device_path(self, volume):
        volume_id = volume.id
        candidate_devices = [
            # kvm or qemu
            'virtio-' + volume_id[:20],
            'scsi-0QEMU_QEMU_HARDDISK_' + volume_id[:20]
        ]

        id_path = '/dev/disk/by-id/'

        if not os.path.exists(id_path):
            return ''

        for dev_name in os.listdir(id_path):
            if dev_name in candidate_devices:
                return id_path + dev_name

        return ''
