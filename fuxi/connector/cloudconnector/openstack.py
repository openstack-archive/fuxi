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
import time

from cinderclient import exceptions as cinder_exception
from novaclient import exceptions as nova_exception
from oslo_concurrency import lockutils
from oslo_concurrency import processutils
from oslo_log import log as logging

from fuxi.common import blockdevice
from fuxi.common import config
from fuxi.common import constants as consts
from fuxi.common import state_monitor
from fuxi.connector import connector
from fuxi import exceptions
from fuxi.i18n import _, _LI, _LW, _LE
from fuxi import utils

CONF = config.CONF

LOG = logging.getLogger(__name__)


class CinderConnector(connector.Connector):
    def __init__(self):
        super(CinderConnector, self).__init__()
        self.cinderclient = utils.get_cinderclient()
        self.novaclient = utils.get_novaclient()

    @lockutils.synchronized('openstack-attach-volume')
    def connect_volume(self, volume, **connect_opts):
        bdm = blockdevice.BlockerDeviceManager()
        ori_devices = bdm.device_scan()

        # Do volume-attach
        try:
            server_id = connect_opts.get('server_id', None)
            if not server_id:
                server_id = utils.get_instance_uuid()

            LOG.info(_LI("Start to connect to volume {0}").format(volume))
            nova_volume = self.novaclient.volumes.create_server_volume(
                server_id=server_id,
                volume_id=volume.id,
                device=None)

            volume_monitor = state_monitor.StateMonitor(
                self.cinderclient,
                nova_volume,
                'in-use',
                ('available', 'attaching',))
            attached_volume = volume_monitor.monitor_cinder_volume()
        except nova_exception.ClientException as ex:
            LOG.error(_LE("Attaching volume {0} to server {1} "
                          "failed. Error: {2}").format(volume.id,
                                                       server_id, ex))
            raise

        # Get all devices on host after do volume-attach,
        # and then find attached device.
        LOG.info(_LI("After connected to volume, scan the added "
                     "block device on host"))
        curr_devices = bdm.device_scan()
        start_time = time.time()
        delta_devices = list(set(curr_devices) - set(ori_devices))
        while not delta_devices:
            time.sleep(consts.DEVICE_SCAN_TIME_DELAY)
            curr_devices = bdm.device_scan()
            delta_devices = list(set(curr_devices) - set(ori_devices))
            if time.time() - start_time > consts.DEVICE_SCAN_TIMEOUT:
                msg = _("Could not detect added device with "
                        "limited time")
                raise exceptions.FuxiException(msg)
        LOG.info(_LI("Get extra added block device {0}"
                     "").format(delta_devices))

        for device in delta_devices:
            if bdm.get_device_size(device) == volume.size:
                device = device.replace('/sys/block', '/dev')
                msg = _LI("Find attached device {0} for volume {1} "
                          "{2}").format(device,
                                        attached_volume.name,
                                        volume)
                LOG.info(msg)

                link_path = os.path.join(consts.VOLUME_LINK_DIR, volume.id)
                try:
                    utils.execute('ln', '-s', device,
                                  link_path,
                                  run_as_root=True)
                except processutils.ProcessExecutionError as e:
                    msg = _LE("Error happened when create link file for "
                              "block device attached by Nova. "
                              "Error: {0}").format(e)
                    LOG.error(msg)
                    raise
                return {'path': link_path}

        LOG.warm(_LW("Could not find matched device"))
        raise exceptions.NotFound("Not Found Matched Device")

    def disconnect_volume(self, volume, **disconnect_opts):
        try:
            volume = self.cinderclient.volumes.get(volume.id)
        except cinder_exception.ClientException as e:
            msg = _LE("Get Volume {0} from Cinder failed").format(volume.id)
            LOG.error(msg)
            raise

        try:
            link_path = self.get_device_path(volume)
            utils.execute('rm', '-f', link_path, run_as_root=True)
        except processutils.ProcessExecutionError as e:
            msg = _LE("Error happened when remove docker volume "
                      "mountpoint directory. Error: {0}").format(e)
            LOG.warn(msg)

        try:
            self.novaclient.volumes.delete_server_volume(
                utils.get_instance_uuid(),
                volume.id)
        except nova_exception.ClientException as e:
            msg = _LE("Detaching volume {0} failed. "
                      "Err: {1}").format(volume.id, e)
            LOG.error(msg)
            raise

        volume_monitor = state_monitor.StateMonitor(self.cinderclient,
                                                    volume,
                                                    'available',
                                                    ('in-use', 'detaching',))
        return volume_monitor.monitor_cinder_volume()

    def get_device_path(self, volume):
        return os.path.join(consts.VOLUME_LINK_DIR, volume.id)
