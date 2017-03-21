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

from fuxi import exceptions
from fuxi import utils

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class Provider(object):
    """Base class for each volume provider.

    Provider provider some operation related with Docker volume provider by
    each backend volume provider, like Cinder.

    """
    volume_provider_type = None

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
    def show(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def mount(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def unmount(self, docker_volume_name):
        pass

    @abc.abstractmethod
    def check_exist(self, docker_volume_name):
        pass

    def _get_mountpoint(self, docker_volume_name):
        """Generate a mount point for volume.

        :param docker_volume_name:
        :rtype: str
        """
        if not docker_volume_name:
            LOG.error("Volume name could not be None")
            raise exceptions.FuxiException("Volume name could not be None")
        if self.volume_provider_type:
            return os.path.join(CONF.volume_dir,
                                self.volume_provider_type,
                                docker_volume_name)
        else:
            return os.path.join(CONF.volume_dir,
                                docker_volume_name)

    def _create_mountpoint(self, mountpoint):
        """Create mount point directory for Docker volume.

        :param mountpoint: The path of Docker volume.
        """
        try:
            if not os.path.exists(mountpoint) or not os.path.isdir(mountpoint):
                utils.execute('mkdir', '-p', '-m=755', mountpoint,
                              run_as_root=True)
                LOG.info("Create mountpoint %s successfully", mountpoint)
        except processutils.ProcessExecutionError as e:
            LOG.error("Error happened when create volume "
                      "directory. Error: %s", e)
            raise

    def _clear_mountpoint(self, mountpoint):
        """Clear mount point directory if it wouldn't used any more.

        :param mountpoint: The path of Docker volume.
        """
        if os.path.exists(mountpoint) and os.path.isdir(mountpoint):
            try:
                utils.execute('rm', '-r', mountpoint, run_as_root=True)
                LOG.info("Clear mountpoint %s successfully", mountpoint)
            except processutils.ProcessExecutionError as e:
                LOG.error("Error happened when clear mountpoint. "
                          "Error: %s", e)
                raise
