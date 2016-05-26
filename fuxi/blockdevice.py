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
import os
import psutil

from fuxi.common import consts
from fuxi.i18n import _LE
from fuxi import utils

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class Partition(object):
    def __init__(self, device, mountpoint, fstype, opts):
        self.device = device
        self.mountpoint = mountpoint
        self.fstype = fstype
        self.opts = opts

    def __repr__(self, *args, **kwargs):
        return str(self.__dict__)


class BlockerDeviceManager(object):
    def make_filesystem(self, devpath, fstype):
        try:
            utils.psutil_execute('mkfs', '-t', fstype, '-F', devpath,
                                 run_as_root=True)
        except processutils.ProcessExecutionError as e:
            with excutils.save_and_reraise_exception():
                msg = _LE("Unexpected error while make filesystem. "
                          "Devpath: {0}, "
                          "Fstype: {1}"
                          "Error: {2}").format(devpath, fstype, e)
                LOG.error(msg)

    def mount(self, devpath, mountpoint):
        try:
            utils.psutil_execute('mount', devpath, mountpoint,
                                 run_as_root=True)
        except processutils.ProcessExecutionError as e:
            with excutils.save_and_reraise_exception():
                msg = _LE("Unexpected error while mount block device. "
                          "Devpath: {0}, "
                          "Mountpoint: {1} "
                          "Error: {2}").format(devpath,
                                               mountpoint,
                                               e)
                LOG.error(msg)

    def unmount(self, devpath):
        try:
            utils.psutil_execute('umount', devpath, run_as_root=True)
        except processutils.ProcessExecutionError as e:
            with excutils.save_and_reraise_exception():
                msg = _LE("Unexpected err while unmount block device. "
                          "Devpath: {0}, "
                          "Error: {1}").format(devpath, e)
                LOG.error(msg)

    def get_mounts(self):
        mounts = psutil.disk_partitions()
        return [Partition(mount.device, mount.mountpoint,
                mount.fstype, mount.opts) for mount in mounts]

    def device_scan(self):
        return glob.glob('/sys/block/*')

    def get_device_size(self, device):
        nr_sectors = open(device + '/size').read().rstrip('\n')
        sect_size = open(device + '/queue/hw_sector_size').read().rstrip('\n')
        return (float(nr_sectors) * float(sect_size)) / consts.G


def _check_aleady_mount(devpath, mountpoint):
    partions = BlockerDeviceManager().get_mounts()
    for p in partions:
        if devpath == p.device and mountpoint == p.mountpoint:
            return True
    return False


def do_mount(devpath, mountpoint, fstype):
    if not _check_aleady_mount(devpath, mountpoint):
        bdm = BlockerDeviceManager()
        try:
            bdm.mount(devpath, mountpoint)
        except processutils.ProcessExecutionError:
            bdm.make_filesystem(devpath, fstype)
            bdm.mount(devpath, mountpoint)
    return mountpoint


def do_unmount(devpath, mountpoint):
    if _check_aleady_mount(devpath, mountpoint):
        BlockerDeviceManager().unmount(devpath)


def get_mountpoint(volume_provider_type, volume_name, volume_id):
    vol_dir = CONF.volume_dir.rstrip('/')
    vol_dir = ''.join([vol_dir, '/', volume_provider_type, '/'])

    try:
        if not os.path.exists(vol_dir) or not os.path.isdir(vol_dir):
            utils.psutil_execute('mkdir', '-p', '-m=700', vol_dir,
                                 run_as_root=True)

        mountpoint = ''.join((vol_dir, volume_name,
                              CONF.volume_joiner, volume_id))
        if not os.path.exists(mountpoint) or not os.path.isdir(mountpoint):
            utils.psutil_execute('mkdir', '-p', '-m=755', mountpoint,
                                 run_as_root=True)
        return mountpoint
    except processutils.ProcessExecutionError as e:
        msg = _LE("Error happened when create volume directory. "
                  "Error: {}").format(e)
        LOG.error(msg)
        raise


def set_mountpoint(attached_volumes):
    partions = BlockerDeviceManager().get_mounts()
    for attached_volume in attached_volumes:
        for partion in partions:
            if attached_volume["devpath"] == partion.device:
                attached_volume["Mountpoint"] = partion.mountpoint


def get_mountpoint_for_device(devpath, mountpoint):
    devpath = os.path.realpath(devpath)
    partions = BlockerDeviceManager().get_mounts()
    for p in partions:
        if devpath == p.device and mountpoint == p.mountpoint:
            return mountpoint
    return ''
