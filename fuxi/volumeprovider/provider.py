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

from fuxi import utils

from oslo_concurrency import processutils


class Provider(object):

    def __init__(self):
        pass

    def create(self, docker_volume_name, volume_opts):
        pass

    def delete(self, docker_volume_name):
        pass

    def list(self):
        pass

    def path(self, docker_volume_name):
        pass

    def show(self, docker_volume_name):
        pass

    def mount(self, docker_volume_name):
        pass

    def unmount(self, docker_volume_name):
        pass

    def check_exist(self, docker_volume_name):
        return False

    def _clear_mountpoint(self, mountpoint):
        if os.path.exists(mountpoint) and os.path.isdir(mountpoint):
            try:
                utils.psutil_execute('rm', '-r', mountpoint)
            except processutils.ProcessExecutionError:
                raise
