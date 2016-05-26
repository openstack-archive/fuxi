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

import abc
import os
import six

from fuxi.i18n import _LE
from fuxi import utils

from oslo_concurrency import processutils
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class Provider(object):
    def __init__(self):
        pass

    @abc.abstractmethod
    def create(self, docker_volume_name, volume_opts):
        pass

    @abc.abstractmethod
    def delete(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def list(self):
        pass

    @abc.abstractmethod
    def path(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def show(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def mount(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def unmount(self, docker_volume_name):
        pass

    def check_exist(self, docker_volume_name):
        return False

    def _clear_mountpoint(self, mountpoint):
        if os.path.exists(mountpoint) and os.path.isdir(mountpoint):
            try:
                utils.psutil_execute('rm', '-r', mountpoint, run_as_root=True)
            except processutils.ProcessExecutionError as e:
                LOG.error(_LE("Error happened when clear mountpoint: "
                              "{0}").format(e))
                raise
