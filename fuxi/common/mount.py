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

from fuxi import exceptions
from fuxi.i18n import _LE
from fuxi import utils

from oslo_concurrency import processutils
from oslo_log import log as logging
from oslo_utils import excutils

proc_mounts_path = '/proc/mounts'

LOG = logging.getLogger(__name__)


class MountInfo(object):
    def __init__(self, device, mountpoint, fstype, opts):
        self.device = device
        self.mountpoint = mountpoint
        self.fstype = fstype
        self.opts = opts

    def __repr__(self, *args, **kwargs):
        return str(self.__dict__)


class Mounter(object):
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

    def unmount(self, mountpoint):
        try:
            utils.execute('umount', mountpoint, run_as_root=True)
        except processutils.ProcessExecutionError as e:
            msg = _LE("Unexpected err while unmount block device. "
                      "Mountpoint: {0}, "
                      "Error: {1}").format(mountpoint, e)
            raise exceptions.UnmountException(msg)

    def read_mounts(self, filter_device=(), filter_fstype=()):
        """Read all mounted filesystems.

        Read all mounted filesystems except filtered option.

        :param filter_device: Filter for device, the result will not contain
                              the mounts whose device argument in it.
        :param filter_fstype: Filter for mount point.
        :return: All mounts.
        """
        (out, err) = processutils.execute('cat', proc_mounts_path,
                                          check_exit_code=0)
        lines = out.split('\n')
        mounts = []
        for line in lines:
            if not line:
                continue
            tokens = line.split()
            if len(tokens) < 4:
                continue
            if tokens[0] in filter_device or tokens[1] in filter_fstype:
                continue
            mounts.append(MountInfo(device=tokens[0], mountpoint=tokens[1],
                                    fstype=tokens[2], opts=tokens[3]))
        return mounts

    def get_mps_by_device(self, devpath):
        """Get all mountpoints that device mounted on.

        :param devpath: The path of mount device.
        :return: All mountpoints.
        :rtype: list
        """
        mps = []
        mounts = self.read_mounts()
        for m in mounts:
            if devpath == m.device:
                mps.append(m.mountpoint)
        return mps


def check_already_mounted(devpath, mountpoint):
    """Check that the mount device is mounted on the specific mount point.

    :param devpath: The path of mount deivce.
    :param mountpoint: The path of mount point.
    :rtype: bool
    """
    mounts = Mounter().read_mounts()
    for m in mounts:
        if devpath == m.device and mountpoint == m.mountpoint:
            return True
    return False


def do_mount(devpath, mountpoint, fstype):
    """Execute device mount operation.

    :param devpath: The path of mount device.
    :param mountpoint: The path of mount point.
    :param fstype: The file system type.
    """
    try:
        if check_already_mounted(devpath, mountpoint):
            return

        mounter = Mounter()
        mounter.mount(devpath, mountpoint, fstype)
    except exceptions.MountException:
        try:
            mounter.make_filesystem(devpath, fstype)
            mounter.mount(devpath, mountpoint, fstype)
        except exceptions.FuxiException as e:
            with excutils.save_and_reraise_exception():
                LOG.error(e.message)
