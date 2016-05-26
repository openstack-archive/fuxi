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
import time
import uuid

from fuxi import blockdevice
from fuxi.common import config
from fuxi.common import consts
from fuxi.connector import connector
from fuxi import exceptions
from fuxi.i18n import _, _LI, _LW, _LE
from fuxi import state_monitor
from fuxi import utils

from oslo_concurrency import processutils

from cinderclient import exceptions as cinder_exception
from novaclient import exceptions as nova_exception

# If CONF.cinder_conf.cloud is True, and then attach volume to this server,
# here will create a link file for attached volume. And link file stored at
# volume_link_dir
volume_link_dir = '/dev/disk/by-id/'

attach_req_list = list()

CONF = config.CONF

LOG = logging.getLogger(__name__)


class CinderConnector(connector.Connector):
    protocol = CONF.cinder.protocol

    def __init__(self):
        super(CinderConnector, self).__init__()
        self.cinderclient = utils.get_cinderclient()
        self.novaclient = utils.get_novaclient()

    def connect_volume(self, volume, **connect_opts):
        # Every time, _nova_attach evoked, generate an uuid for distinguish
        # every request.
        mid = uuid.uuid4()
        attach_req_list.append(mid)
        LOG.info("Attach_rep_list after evoke method _nova_attach: "
                 "{0}".format(attach_req_list))
        curr_mid = attach_req_list[0]
        while curr_mid != mid:
            time.sleep(0.5)
            curr_mid = attach_req_list[0]

        # Here need to validate volume attached to other server.
        try:
            bdm = blockdevice.BlockerDeviceManager()
            ori_devices = bdm.device_scan()

            # Do volume-attach
            try:
                server_id = connect_opts.get('server_id', None)
                if not server_id:
                    server_id = utils.get_instance_uuid()

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
            curr_devices = bdm.device_scan()
            start_time = time.time()
            delta_devices = list(set(curr_devices) - set(ori_devices))
            while not delta_devices:
                time.sleep(consts.DEVICE_SCAN_TIME_DELAY)
                curr_devices = bdm.device_scan()
                delta_devices = list(set(curr_devices) - set(ori_devices))
                if time.time() - start_time > consts.DEVICE_SCAN_TIMEOUT:
                    msg = _("Could not detect added device with "
                            "limited time.")
                    raise exceptions.FuxiException(msg)

            for device in delta_devices:
                if bdm.get_device_size(device) == volume.size:
                    device = device.replace('/sys/block', '/dev')
                    msg = _LI("Find attached device {0} for volume {1} "
                              "{2}").format(device,
                                            attached_volume.name,
                                            volume)
                    LOG.info(msg)

                    link_vol_id_path = volume_link_dir + volume.id
                    try:
                        utils.psutil_execute('ln', '-s', device,
                                             link_vol_id_path,
                                             run_as_root=True)
                    except processutils.ProcessExecutionError:
                        raise
                    return attached_volume, device

            LOG.warm(_LW("Could not find matched device."))
            raise exceptions.NotFound("Not Found Matched Device")
        finally:
            attach_req_list.remove(mid)

    def disconnect_volume(self, volume, **disconnect_opts):
        try:
            volume = self.cinderclient.volumes.get(volume.id)
        except cinder_exception.ClientException as e:
            msg = _LE("Get Volume {} from cinder failed.").format(volume.id)
            LOG.error(msg)
            raise

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
        return volume_link_dir + volume.id
