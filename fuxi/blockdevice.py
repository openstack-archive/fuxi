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

from fuxi import exceptions
from fuxi.i18n import _LE
from fuxi import utils

from oslo_concurrency import processutils
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import units

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
            utils.execute('mkfs', '-t', fstype, '-F', devpath,
                          run_as_root=True)
        except processutils.ProcessExecutionError as e:
            msg = _LE("Unexpected error while make filesystem. "
                      "Devpath: {0}, "
                      "Fstype: {1}"
                      "Error: {2}").format(devpath, fstype, e)
            raise exceptions.MakeFileSystemException(msg)

    def mount(self, devpath, mountpoint, fstype=None):
        try:
            if fstype:
                utils.execute('mount', '-t', fstype, devpath, mountpoint,
                              run_as_root=True)
            else:
                utils.execute('mount', devpath, mountpoint,
                              run_as_root=True)
        except processutils.ProcessExecutionError as e:
            msg = _LE("Unexpected error while mount block device. "
                      "Devpath: {0}, "
                      "Mountpoint: {1} "
                      "Error: {2}").format(devpath, mountpoint, e)
            raise exceptions.MountException(msg)

    def unmount(self, devpath):
        try:
            utils.execute('umount', devpath, run_as_root=True)
        except processutils.ProcessExecutionError as e:
            msg = _LE("Unexpected err while unmount block device. "
                      "Devpath: {0}, "
                      "Error: {1}").format(devpath, e)
            raise exceptions.UnmountException(msg)

    def get_mounts(self):
        mounts = psutil.disk_partitions()
        return [Partition(mount.device, mount.mountpoint,
                mount.fstype, mount.opts) for mount in mounts]

    def device_scan(self):
        return glob.glob('/sys/block/*')

    def get_device_size(self, device):
        nr_sectors = open(device + '/size').read().rstrip('\n')
        sect_size = open(device + '/queue/hw_sector_size').read().rstrip('\n')
        return (float(nr_sectors) * float(sect_size)) / units.Gi


def _check_aleady_mount(devpath, mountpoint):
    partions = BlockerDeviceManager().get_mounts()
    for p in partions:
        if devpath == p.device and mountpoint == p.mountpoint:
            return True
    return False


def do_mount(devpath, mountpoint, fstype):
    try:
        if _check_aleady_mount(devpath, mountpoint):
            return

        bdm = BlockerDeviceManager()
        bdm.mount(devpath, mountpoint, fstype)
    except exceptions.MountException:
        try:
            bdm.make_filesystem(devpath, fstype)
            bdm.mount(devpath, mountpoint, fstype)
        except exceptions.FuxiException as e:
            with excutils.save_and_reraise_exception():
                LOG.error(e.message)


def do_unmount(devpath, mountpoint):
    try:
        if _check_aleady_mount(devpath, mountpoint):
            BlockerDeviceManager().unmount(devpath)
    except exceptions.UnmountException as e:
        with excutils.save_and_reraise_exception():
            LOG.error(e.message)


def create_mountpoint(mountpoint):
    """Create mount point for block device(Volume).

    :param mountpoint: The expected mount point
    :return:
    """
    try:
        if not os.path.exists(mountpoint) or not os.path.isdir(mountpoint):
            utils.execute('mkdir', '-p', '-m=755', mountpoint,
                          run_as_root=True)
    except processutils.ProcessExecutionError as e:
        msg = _LE("Error happened when create volume directory. "
                  "Error: {0}").format(e)
        LOG.error(msg)
        raise


def get_mountpoint_for_device(devpath, mountpoint):
    """Get the mount point for mounted block device.

    :param devpath: The path of block device.
    :param mountpoint: The expected mount point path.
    :return: The real mount point path.
    """
    devpath = os.path.realpath(devpath)
    partions = BlockerDeviceManager().get_mounts()
    for p in partions:
        if devpath == p.device and mountpoint == p.mountpoint:
            return mountpoint
    return ''
