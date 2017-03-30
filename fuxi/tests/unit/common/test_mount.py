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

from fuxi.common import mount
from fuxi import exceptions
from fuxi.tests.unit import base


class FakeMounter(object):
    def __init__(self, mountinfo=None):
        self.mountinfo = "/dev/0 /path/to/0 type0 flags 0 0\n" \
                         "/dev/1 /path/to/1 type1 flags 0 0\n" \
                         "/dev/2 /path/to/2 type2 flags,1,2=3 0 0\n" \
            if not mountinfo else mountinfo

    def mount(self, devpath, mountpoint, fstype=None):
        if not fstype:
            fstype = 'ext4'
        self.mountinfo += ' '.join([devpath, mountpoint, fstype,
                                    'flags', '0', '0\n'])

    def unmount(self, mountpoint):
        mounts = self.read_mounts()
        ori_len = len(mounts)
        for m in mounts:
            if m.mountpoint == mountpoint:
                mounts.remove(m)
        if ori_len != len(mounts):
            self.mountinfo = ''.join([' '.join([m.device, m.mountpoint,
                                                m.fstype, m.opts,
                                                '0', '0\n'])
                                      for m in mounts])
        else:
            raise exceptions.UnmountException()

    def read_mounts(self, filter_device=(), filter_fstype=()):
        lines = self.mountinfo.split('\n')
        mounts = []
        for line in lines:
            if not line:
                continue
            tokens = line.split()
            if len(tokens) < 4:
                continue
            if tokens[0] in filter_device or tokens[1] in filter_fstype:
                continue
            mounts.append(mount.MountInfo(device=tokens[0],
                                          mountpoint=tokens[1],
                                          fstype=tokens[2], opts=tokens[3]))
        return mounts

    def get_mps_by_device(self, devpath):
        mps = []
        mounts = self.read_mounts()
        for m in mounts:
            if devpath in m.device:
                mps.append(m.mountpoint)
        return mps


def check_already_mounted(devpath, mountpoint):
    mounts = FakeMounter().read_mounts()
    for m in mounts:
        if m.device == devpath and m.mountpoint == mountpoint:
            return True
    return False


class TestMounter(base.TestCase):
    def test_mount(self):
        fake_devpath = '/dev/3'
        fake_mp = '/path/to/3'
        fake_fstype = 'ext4'
        fake_mounter = FakeMounter()
        fake_mounter.mount(fake_devpath, fake_mp, fake_fstype)
        fake_mountinfo = "/dev/0 /path/to/0 type0 flags 0 0\n" \
                         "/dev/1 /path/to/1 type1 flags 0 0\n" \
                         "/dev/2 /path/to/2 type2 flags,1,2=3 0 0\n" \
                         "/dev/3 /path/to/3 ext4 flags 0 0\n"
        self.assertEqual(fake_mountinfo, fake_mounter.mountinfo)

    def test_unmount(self):
        fake_mp = '/path/to/2'
        fake_mounter = FakeMounter()
        fake_mounter.unmount(fake_mp)
        fake_mountinfo = "/dev/0 /path/to/0 type0 flags 0 0\n" \
                         "/dev/1 /path/to/1 type1 flags 0 0\n"
        self.assertEqual(fake_mountinfo, fake_mounter.mountinfo)

    def test_read_mounts(self):
        fake_mounts = [str(mount.MountInfo('/dev/0', '/path/to/0',
                                           'type0', 'flags')),
                       str(mount.MountInfo('/dev/1', '/path/to/1',
                                           'type1', 'flags')),
                       str(mount.MountInfo('/dev/2', '/path/to/2',
                                           'type2', 'flags,1,2=3'))]
        mounts = [str(m) for m in FakeMounter().read_mounts()]
        self.assertEqual(len(fake_mounts), len(mounts))
        for m in mounts:
            self.assertIn(m, fake_mounts)

    def test_get_mps_by_device(self):
        self.assertEqual(['/path/to/0'],
                         FakeMounter().get_mps_by_device('/dev/0'))

    def test_check_alread_mounted(self):
        self.assertTrue(check_already_mounted('/dev/0', '/path/to/0'))
        self.assertFalse(check_already_mounted('/dev/0', '/path/to/1'))
