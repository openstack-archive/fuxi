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

from fuxi import blockdevice
from fuxi.common import consts
from fuxi import exceptions
from fuxi.i18n import _, _LE, _LI, _LW
from fuxi import state_monitor
from fuxi import utils
from fuxi.volumeprovider import provider

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils
from oslo_utils import strutils

from cinderclient import exceptions as cinder_exception

CONF = cfg.CONF
CONF.import_group('keystone', 'fuxi.common.config')
CONF.import_group('cinder', 'fuxi.common.config')

keystone_conf = CONF.keystone
cinder_conf = CONF.cinder

# If CONF.volume_connector is OPENSTACK, and then attach volume to this server,
# here will create a link file for attached volume. And link file stored at
# volume_link_dir
volume_link_dir = '/dev/disk/by-id/'

# volume states
UNKNOWN = consts.UNKNOWN
NOT_ATTACH = consts.NOT_ATTACH
ATTACH_TO_THIS = consts.ATTACH_TO_THIS
ATTACH_TO_OTHER = consts.ATTACH_TO_OTHER

OPENSTACK = 'openstack'
OSBRICK = 'osbrick'

volume_connector_conf = {
    OPENSTACK: 'fuxi.connector.cloudconnector.openstack.CinderConnector',
    OSBRICK: 'fuxi.connector.osbrickconnector.CinderConnector'}

LOG = logging.getLogger(__name__)


class Cinder(provider.Provider):
    volume_provider_type = 'cinder'

    def __init__(self):
        super(Cinder, self).__init__()
        self.cinderclient = utils.get_cinderclient()

    def _get_connector(self):
        _connector = CONF.volume_connector
        if not _connector or _connector not in volume_connector_conf:
            msg = _LE("Must provide an valid volume connector.")
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        return importutils.import_class(volume_connector_conf[_connector])()

    def create(self, docker_volume_name, volume_opts):
        if not volume_opts:
            volume_opts = {}

        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)

        if state == ATTACH_TO_THIS:
            LOG.warn(_LI("The volume {0} {1} already exists and attached to "
                         "this server.").format(docker_volume_name,
                                                cinder_volume))
            return
        elif state == NOT_ATTACH:
            LOG.warn(_LE("The volume {0} {1} is already exists but not "
                         "attached").format(docker_volume_name,
                                            cinder_volume))
            connector.connect_volume(cinder_volume)
            return
        elif state == ATTACH_TO_OTHER:
            if cinder_volume.multiattach:
                fstype = volume_opts.get('fstype', CONF.fstype)
                vol_fstype = cinder_volume.metadata.get('fstype', CONF.fstype)
                if fstype != vol_fstype:
                    msg = _LE("Volume already exists with fstype: {0}, but "
                              "currently provided fstype is {1}, not "
                              "match.").format(vol_fstype, fstype)
                    LOG.error(msg)
                    raise exceptions.FuxiException('FSType Not Match')
                connector.connect_volume(cinder_volume)
                return
            else:
                msg = _LE("The volume {0} {1} is already attached to another "
                          "server").format(docker_volume_name, cinder_volume)
                LOG.error(msg)
                raise exceptions.FuxiException(msg)
        elif state == UNKNOWN:
            volume_opts['name'] = docker_volume_name
            cinder_volume = self._create_volume(docker_volume_name,
                                                volume_opts)
            connector.connect_volume(cinder_volume)
            return

    def _create_volume(self, docker_volume_name, volume_opts):
        if not volume_opts:
            volume_opts = {}

        if 'size' in volume_opts:
            try:
                size = int(volume_opts['size'])
            except ValueError:
                LOG.error(_LE("Volume size must able to convert to int type."))
                raise
        else:
            size = CONF.default_volume_size
            msg = _LI("Volume size doesn't provide from command, so use "
                      "default size {0}G.").format(size)
            LOG.info(msg)

        availability_zone = (volume_opts.get('availability_zone', None)
                             or cinder_conf.availability_zone)
        volume_type = (volume_opts.get('volume_type', None)
                       or cinder_conf.volume_type)
        fstype = volume_opts.get('fstype', None) or CONF.fstype
        scheduler_hints = volume_opts.get('scheduler_hints', None)
        req_multiattach = volume_opts.get('multiattach',
                                          cinder_conf.multiattach)
        multiattach = strutils.bool_from_string(req_multiattach, strict=True)

        metadata = {consts.VOLUME_FROM: CONF.volume_from,
                    'fstype': fstype}

        try:
            LOG.info(_LI("Start create volume {0} from "
                         "Cinder").format(docker_volume_name))
            volume = self.cinderclient.volumes.create(
                size=size,
                name=docker_volume_name,
                volume_type=volume_type,
                availability_zone=availability_zone,
                metadata=metadata,
                scheduler_hints=scheduler_hints,
                multiattach=multiattach)
        except cinder_exception.ClientException as e:
            msg = _LE("Error happened when create an volume {0} from Cinder. "
                      "Error: {1}").format(docker_volume_name, e)
            LOG.error(msg)
            raise

        volume_monitor = state_monitor.StateMonitor(self.cinderclient,
                                                    volume,
                                                    'available',
                                                    ('creating',))
        return volume_monitor.monitor_cinder_volume()

    def delete(self, docker_volume_name):
        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)

        if state == ATTACH_TO_THIS:
            # Unmount block device.
            self._unmount(docker_volume_name, cinder_volume)

            # Detach device from this server.
            connector.disconnect_volume(cinder_volume)

            available_volume = self.cinderclient.volumes.get(cinder_volume.id)
            # If this volume is not used by other server any more,
            # than delete it from Cinder.
            if not available_volume.attachments:
                msg = _LW("No other servers still use this volume {0} "
                          "{1} any more, so delete it from Cinder."
                          "").format(docker_volume_name, cinder_volume)
                LOG.warn(msg)
                self._delete_volume(available_volume)
            return True
        elif state == UNKNOWN:
            return False
        else:
            msg = _LE("The volume {0} {1} state must be {2} when "
                      "remove it from this server, but current state "
                      "is {3}").format(docker_volume_name,
                                       cinder_volume,
                                       ATTACH_TO_THIS,
                                       state)
            LOG.error(msg)
            raise exceptions.NotMatchedState(msg)

    def _unmount(self, docker_volume_name, cinder_volume):
        mountpoint = blockdevice.get_mountpoint(self.volume_provider_type,
                                                docker_volume_name,
                                                cinder_volume.id)
        connector = self._get_connector()
        # NOVA VOLUME-ATTACH no link-devpath, so remove action will failed.
        # Docker volume ls could show it.
        devpath = os.path.realpath(connector.get_device_path(cinder_volume))

        if not devpath or not os.path.exists(devpath):
            msg_ft = _LE("Could not find device path for volume {0} {1} in "
                         "host.").format(docker_volume_name, cinder_volume)
            LOG.error(msg_ft)
            raise exceptions.FuxiException(msg_ft)

        blockdevice.do_unmount(devpath, mountpoint)

        LOG.warn(_LW("Clear mountpoint {0} for volume "
                     "{1}").format(mountpoint, docker_volume_name))
        self._clear_mountpoint(mountpoint)

        if CONF.volume_connector == OPENSTACK:
            try:
                utils.psutil_execute('rm', '-r',
                                     connector.get_device_path(cinder_volume),
                                     run_as_root=True)
            except processutils.ProcessExecutionError as e:
                msg = _LE("Error happened when remove docker volume "
                          "mountpoint directory. Error: {0}").format(e)
                LOG.warn(msg)

            # os.remove(connector.get_device_path(cinder_volume))

    def _delete_volume(self, volume):
        try:
            self.cinderclient.volumes.delete(volume)
        except cinder_exception.NotFound:
            return
        except cinder_exception.ClientException as e:
            msg = _LE("Error happened when delete volume from Cinder. "
                      "Error: {0}").format(e)
            LOG.error(msg)
            raise

        start_time = time.time()
        # Wait until the volume is not there or until the operation
        # timesout
        while(time.time() - start_time < consts.DESTROY_VOLUME_TIMEOUT):
            try:
                self.cinderclient.volumes.get(volume.id)
            except cinder_exception.NotFound:
                return
            time.sleep(consts.VOLUME_SCAN_TIME_DELAY)

        # If the volume is not deleted, raise an exception
        msg_ft = _LE("Timed out while waiting for volume. "
                     "Expected Volume: {0}, "
                     "Expected State: {1}, "
                     "Elapsed Time: {2}").format(volume,
                                                 None,
                                                 time.time() - start_time)
        raise exceptions.TimeoutException(msg_ft)

    def list(self):
        _connector = CONF.volume_connector

        docker_volumes = []
        try:
            search_opts = {'metadata': {consts.VOLUME_FROM: 'fuxi'}}
            for vol in self.cinderclient.volumes.list(search_opts=search_opts):
                docker_volume_name = vol.name
                if not docker_volume_name or not vol.attachments:
                    continue

                for am in vol.attachments:
                    vpt = self.volume_provider_type
                    mountpoint = blockdevice.get_mountpoint(vpt,
                                                            docker_volume_name,
                                                            vol.id)
                    if ((_connector == OPENSTACK
                            and am['server_id'] == utils.get_instance_uuid())
                            or (_connector == OSBRICK
                                and am['host_name'] == utils.get_hostname())):
                        devpath = self._get_connector().get_device_path(vol)
                        mountpoint = \
                            blockdevice.get_mountpoint_for_device(devpath,
                                                                  mountpoint)
                        docker_vol = {'Name': docker_volume_name,
                                      'Mountpoint': mountpoint}
                        docker_volumes.append(docker_vol)
        except cinder_exception.ClientException as e:
            LOG.error(_LE("Retrieve volume list failed. Error: {0}").format(e))
            raise
        return docker_volumes

    def path(self, docker_volume_name):
        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)

        if state == UNKNOWN:
            msg = _LW("Volume {0} doesn't exist in "
                      "Cinder").format(docker_volume_name)
            LOG.error(msg)
            raise exceptions.NotFound(msg)
        elif state == ATTACH_TO_THIS:
            devpath = connector.get_device_path(cinder_volume)
            mountpoint = blockdevice.get_mountpoint(self.volume_provider_type,
                                                    docker_volume_name,
                                                    cinder_volume.id)
            return blockdevice.get_mountpoint_for_device(devpath, mountpoint)
        elif state == NOT_ATTACH:
            msg = _LW("Volume {0} {1} exists, but not "
                      "attached.").format(docker_volume_name, cinder_volume)
            LOG.warn(msg)
            raise exceptions.FuxiException(msg)
        elif state == ATTACH_TO_OTHER:
            msg = _LE("Volume {0} {1} exists, but attached "
                      "to other server.").format(docker_volume_name,
                                                 cinder_volume)
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        raise exceptions.NotMatchedState

    def show(self, docker_volume_name):
        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)

        if state == ATTACH_TO_THIS:
            devpath = connector.get_device_path(cinder_volume)
            mountpoint = blockdevice.get_mountpoint(self.volume_provider_type,
                                                    docker_volume_name,
                                                    cinder_volume.id)
            LOG.info("Expected devpath: {0} and mountpoint: {1} for volume: "
                     "{2} {3}".format(devpath, mountpoint, docker_volume_name,
                                      cinder_volume))
            return blockdevice.get_mountpoint_for_device(devpath, mountpoint)
        elif state == UNKNOWN:
            msg = _LW("Can't find this volume '{0}' in "
                      "Cinder").format(docker_volume_name)
            LOG.warn(msg)
            raise exceptions.NotFound(msg)
        else:
            msg = _LE("Volume '{0}' exists, but not attached to this volume,"
                      "and current state is {1}").format(docker_volume_name,
                                                         state)
            raise exceptions.FuxiException(msg)

    def _get_docker_volume(self, docker_volume_name):
        _volume_connector = CONF.volume_connector
        try:
            search_opts = {'name': docker_volume_name,
                           'metadata': {consts.VOLUME_FROM: CONF.volume_from}}
            for vol in self.cinderclient.volumes.list(search_opts=search_opts):
                if vol.name == docker_volume_name:
                    if vol.attachments:
                        for am in vol.attachments:
                            if _volume_connector == OPENSTACK:
                                if (am['server_id']
                                        == utils.get_instance_uuid()):
                                    return vol, ATTACH_TO_THIS
                            elif _volume_connector == OSBRICK:
                                if am['host_name'] == utils.get_hostname():
                                    return vol, ATTACH_TO_THIS
                        return vol, ATTACH_TO_OTHER
                    else:
                        return vol, NOT_ATTACH
            return None, UNKNOWN
        except cinder_exception.ClientException as ex:
            LOG.error(_LE("Error happened while getting volume list "
                          "information from cinder. Error: {0}").format(ex))
            raise
        except Exception as e:
            LOG.error(_LE("Error happened. Error: {0}").format(e))
            raise

    def mount(self, docker_volume_name):
        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)

        if state != ATTACH_TO_THIS:
            msg = _("Volume {0} is not in correct state, current state "
                    "is {1}").format(docker_volume_name, state)
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        if CONF.volume_connector == OPENSTACK:
            if not os.path.exists(connector.get_device_path(cinder_volume)):
                LOG.warn(_LW("Could not find device link file, "
                             "so rebuild it."))
                connector.disconnect_volume(cinder_volume)
                connector.connect_volume(cinder_volume)

        devpath = os.path.realpath(connector.get_device_path(cinder_volume))

        if not devpath or not os.path.exists(devpath):
            msg = _("Can't find volume device path")
            LOG.error(msg)
            raise exceptions.FuxiException(msg)
        mountpoint = blockdevice.get_mountpoint(self.volume_provider_type,
                                                docker_volume_name,
                                                cinder_volume.id)
        fstype = cinder_volume.metadata.get('fstype', CONF.fstype)

        blockdevice.do_mount(devpath, mountpoint, fstype)

        return mountpoint

    def unmount(self, docker_volume_name):
        return

    def check_exist(self, docker_volume_name):
        _, state = self._get_docker_volume(docker_volume_name)
        if state == UNKNOWN:
            return False
        return True
