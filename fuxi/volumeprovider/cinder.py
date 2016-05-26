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
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils
from oslo_utils import strutils

from fuxi.common import constants as consts
from fuxi.common import mount
from fuxi.common import state_monitor
from fuxi import exceptions
from fuxi.i18n import _, _LE, _LI, _LW
from fuxi import utils
from fuxi.volumeprovider import provider

CONF = cfg.CONF
CONF.import_group('keystone', 'fuxi.common.config')
CONF.import_group('cinder', 'fuxi.common.config')

keystone_conf = CONF.keystone
cinder_conf = CONF.cinder

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


def get_cinder_volume_kwargs(docker_volume_name, docker_volume_opt):
    """Retrieve parameters for creating Cinder volume.

    Retrieve required parameters and remove unsupported arguments from
    client input. These parameters are used to create a Cinder volume.

    :param docker_volume_name: Name for Cinder volume
    :type docker_volume_name: str
    :param docker_volume_opt: Optional parameters for Cinder volume
    :type docker_volume_opt: dict
    :rtype: dict
    """
    options = ['size', 'consistencygroup_id', 'snapshot_id', 'source_volid',
               'description', 'volume_type', 'user_id', 'project_id',
               'availability_zone', 'scheduler_hints', 'source_replica',
               'multiattach']
    kwargs = {}

    if 'size' in docker_volume_opt:
        try:
            size = int(docker_volume_opt.pop('size'))
        except ValueError:
            LOG.error(_LE("Volume size must able to convert to int type"))
            raise
    else:
        size = CONF.default_volume_size
        msg = _LI("Volume size doesn't provide from command, so use "
                  "default size {0}G").format(size)
        LOG.info(msg)
    kwargs['size'] = size

    for key, value in docker_volume_opt.items():
        if key in options:
            kwargs[key] = value

    if not kwargs.get('availability_zone', None):
        kwargs['availability_zone'] = cinder_conf.availability_zone

    if not kwargs.get('volume_type', None):
        kwargs['volume_type'] = cinder_conf.volume_type

    kwargs['name'] = docker_volume_name
    kwargs['metadata'] = {consts.VOLUME_FROM: CONF.volume_from,
                          'fstype': kwargs.pop('fstype', cinder_conf.fstype)}

    req_multiattach = kwargs.pop('multiattach', cinder_conf.multiattach)
    kwargs['multiattach'] = strutils.bool_from_string(req_multiattach,
                                                      strict=True)

    return kwargs


def get_host_id():
    """Get a value that could represent this server.

    :return:
    """
    host_id = None
    volume_connector = cinder_conf.volume_connector
    if volume_connector == OPENSTACK:
        host_id = utils.get_instance_uuid()
    elif volume_connector == OSBRICK:
        host_id = utils.get_hostname().lower()
    return host_id


class Cinder(provider.Provider):
    volume_provider_type = 'cinder'

    def __init__(self):
        super(Cinder, self).__init__()
        self.cinderclient = utils.get_cinderclient()

    def _get_connector(self):
        _connector = cinder_conf.volume_connector
        if not _connector or _connector not in volume_connector_conf:
            msg = _LE("Must provide an valid volume connector")
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        return importutils.import_class(volume_connector_conf[_connector])()

    def _get_docker_volume(self, docker_volume_name):
        LOG.info(_LI("Retrieve docker volume {0} from "
                     "Cinder").format(docker_volume_name))

        try:
            host_id = get_host_id()

            volume_connector = cinder_conf.volume_connector
            search_opts = {'name': docker_volume_name,
                           'metadata': {consts.VOLUME_FROM: CONF.volume_from}}
            for vol in self.cinderclient.volumes.list(search_opts=search_opts):
                if vol.name == docker_volume_name:
                    if vol.attachments:
                        for am in vol.attachments:
                            if volume_connector == OPENSTACK:
                                if am['server_id'] == host_id:
                                    return vol, ATTACH_TO_THIS
                            elif volume_connector == OSBRICK:
                                if am['host_name'].lower() == host_id:
                                    return vol, ATTACH_TO_THIS
                        return vol, ATTACH_TO_OTHER
                    else:
                        return vol, NOT_ATTACH
            return None, UNKNOWN
        except cinder_exception.ClientException as ex:
            LOG.error(_LE("Error happened while getting volume list "
                          "information from cinder. Error: {0}").format(ex))
            raise

    def _check_attached_to_this(self, cinder_volume):
        host_id = get_host_id()
        vol_conn = cinder_conf.volume_connector
        for am in cinder_volume.attachments:
            if vol_conn == OPENSTACK and am['server_id'] == host_id:
                return True
            elif vol_conn == OSBRICK and am['host_name'].lower() == host_id:
                return True
        return False

    def _create_volume(self, docker_volume_name, volume_opts):
        LOG.info(_LI("Start to create docker volume {0} from "
                     "Cinder").format(docker_volume_name))

        cinder_volume_kwargs = get_cinder_volume_kwargs(docker_volume_name,
                                                        volume_opts)

        try:
            volume = self.cinderclient.volumes.create(**cinder_volume_kwargs)
        except cinder_exception.ClientException as e:
            msg = _LE("Error happened when create an volume {0} from Cinder. "
                      "Error: {1}").format(docker_volume_name, e)
            LOG.error(msg)
            raise

        LOG.info(_LI("Waiting volume {0} to be available").format(volume))
        volume_monitor = state_monitor.StateMonitor(
            self.cinderclient,
            volume,
            'available',
            ('creating',),
            time_delay=consts.VOLUME_SCAN_TIME_DELAY)
        volume = volume_monitor.monitor_cinder_volume()

        LOG.info(_LI("Create docker volume {0} {1} from Cinder "
                     "successfully").format(docker_volume_name, volume))
        return volume

    def create(self, docker_volume_name, volume_opts):
        if not volume_opts:
            volume_opts = {}

        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} {1} with state "
                     "{2}").format(docker_volume_name, cinder_volume, state))

        device_info = {}
        if state == ATTACH_TO_THIS:
            LOG.warn(_LW("The volume {0} {1} already exists and attached to "
                         "this server").format(docker_volume_name,
                                               cinder_volume))
            device_info = {'path': connector.get_device_path(cinder_volume)}
        elif state == NOT_ATTACH:
            LOG.warn(_LW("The volume {0} {1} is already exists but not "
                         "attached").format(docker_volume_name,
                                            cinder_volume))
            device_info = connector.connect_volume(cinder_volume)
        elif state == ATTACH_TO_OTHER:
            if cinder_volume.multiattach:
                fstype = volume_opts.get('fstype', cinder_conf.fstype)
                vol_fstype = cinder_volume.metadata.get('fstype',
                                                        cinder_conf.fstype)
                if fstype != vol_fstype:
                    msg = _LE("Volume already exists with fstype: {0}, but "
                              "currently provided fstype is {1}, not "
                              "match").format(vol_fstype, fstype)
                    LOG.error(msg)
                    raise exceptions.FuxiException('FSType Not Match')
                device_info = connector.connect_volume(cinder_volume)
            else:
                msg = _LE("The volume {0} {1} is already attached to another "
                          "server").format(docker_volume_name, cinder_volume)
                LOG.error(msg)
                raise exceptions.FuxiException(msg)
        elif state == UNKNOWN:
            volume_opts['name'] = docker_volume_name
            cinder_volume = self._create_volume(docker_volume_name,
                                                volume_opts)
            device_info = connector.connect_volume(cinder_volume)

        return device_info

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
        # Wait until the volume is not there or until the operation timeout
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

    def delete(self, docker_volume_name):
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} {1} with state "
                     "{2}").format(docker_volume_name, cinder_volume, state))

        if state == ATTACH_TO_THIS:
            link_path = self._get_connector().get_device_path(cinder_volume)
            if not link_path or not os.path.exists(link_path):
                msg = _LE(
                    "Could not find device link path for volume {0} {1} "
                    "in host").format(docker_volume_name, cinder_volume)
                LOG.error(msg)
                raise exceptions.FuxiException(msg)

            devpath = os.path.realpath(link_path)
            if not os.path.exists(devpath):
                msg = _LE("Could not find device path for volume {0} {1} in "
                          "host").format(docker_volume_name, cinder_volume)
                LOG.error(msg)
                raise exceptions.FuxiException(msg)

            ref_count = mount.mount_device_ref_count(devpath)
            if ref_count > 0:
                mountpoint = self._get_mountpoint(docker_volume_name)
                if mount.check_already_mounted(devpath, mountpoint):
                    mount.Mounter().unmount(mountpoint)

                    self._clear_mountpoint(mountpoint)
                    LOG.warn(_LW("Clear mountpoint {0} for volume {1} "
                                 "successfully").format(mountpoint,
                                                        docker_volume_name))

                    # If this volume is still mounted on other mount point,
                    # then return.
                    if ref_count > 1:
                        return True
                else:
                    return True

            # Detach device from this server.
            self._get_connector().disconnect_volume(cinder_volume)

            # Delete the link path for device.
            try:
                utils.execute('rm', '-r', link_path,
                              run_as_root=True)
            except processutils.ProcessExecutionError as e:
                msg = _LE("Error happened when remove docker volume "
                          "mountpoint directory. Error: {0}").format(e)
                LOG.warn(msg)

            available_volume = self.cinderclient.volumes.get(cinder_volume.id)
            # If this volume is not used by other server any more,
            # than delete it from Cinder.
            if not available_volume.attachments:
                msg = _LW("No other servers still use this volume {0} "
                          "{1} any more, so delete it from Cinder"
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

    def list(self):
        LOG.info(_LI("Start to retrieve all docker volumes from Cinder"))

        docker_volumes = []
        try:
            search_opts = {'metadata': {consts.VOLUME_FROM: 'fuxi'}}
            for vol in self.cinderclient.volumes.list(search_opts=search_opts):
                docker_volume_name = vol.name
                if not docker_volume_name or not vol.attachments:
                    continue

                mountpoint = self._get_mountpoint(vol.name)
                if self._check_attached_to_this(vol):
                    devpath = self._get_connector().get_device_path(vol)
                    mountpoint = mount.get_mountpoint_for_device(devpath,
                                                                 mountpoint)
                    docker_vol = {'Name': docker_volume_name,
                                  'Mountpoint': mountpoint}
                    docker_volumes.append(docker_vol)
        except cinder_exception.ClientException as e:
            LOG.error(_LE("Retrieve volume list failed. Error: {0}").format(e))
            raise

        LOG.info(_LI("Retrieve docker volumes {0} from Cinder "
                     "successfully").format(docker_volumes))
        return docker_volumes

    def path(self, docker_volume_name):
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} {1} with state "
                     "{2}").format(docker_volume_name, cinder_volume, state))

        if state == UNKNOWN:
            msg = _LW("Volume {0} doesn't exist in "
                      "Cinder").format(docker_volume_name)
            LOG.error(msg)
            raise exceptions.NotFound(msg)
        elif state == ATTACH_TO_THIS:
            devpath = self._get_connector().get_device_path(cinder_volume)
            mountpoint = self._get_mountpoint(docker_volume_name)
            return mount.get_mountpoint_for_device(devpath, mountpoint)
        elif state == NOT_ATTACH:
            msg = _LW("Volume {0} {1} exists, but not "
                      "attached").format(docker_volume_name, cinder_volume)
            LOG.warn(msg)
            raise exceptions.FuxiException(msg)
        elif state == ATTACH_TO_OTHER:
            msg = _LE("Volume {0} {1} exists, but attached "
                      "to other server").format(docker_volume_name,
                                                cinder_volume)
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        raise exceptions.NotMatchedState

    def show(self, docker_volume_name):
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} {1} with state "
                     "{2}").format(docker_volume_name, cinder_volume, state))

        if state == ATTACH_TO_THIS:
            devpath = self._get_connector().get_device_path(cinder_volume)
            mountpoint = self._get_mountpoint(docker_volume_name)
            LOG.info("Expected devpath: {0} and mountpoint: {1} for volume: "
                     "{2} {3}".format(devpath, mountpoint, docker_volume_name,
                                      cinder_volume))
            return mount.get_mountpoint_for_device(devpath, mountpoint)
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

    def mount(self, docker_volume_name):
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} {1} with state "
                     "{2}").format(docker_volume_name, cinder_volume, state))

        if state != ATTACH_TO_THIS:
            msg = _("Volume {0} is not in correct state, current state "
                    "is {1}").format(docker_volume_name, state)
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        connector = self._get_connector()

        link_path = connector.get_device_path(cinder_volume)
        if not os.path.exists(link_path):
            LOG.warn(_LW("Could not find device link file, "
                         "so rebuild it"))
            connector.disconnect_volume(cinder_volume)
            connector.connect_volume(cinder_volume)

        devpath = os.path.realpath(link_path)
        if not devpath or not os.path.exists(devpath):
            msg = _("Can't find volume device path")
            LOG.error(msg)
            raise exceptions.FuxiException(msg)

        mountpoint = self._get_mountpoint(docker_volume_name)
        self._create_mountpoint(mountpoint)

        fstype = cinder_volume.metadata.get('fstype', cinder_conf.fstype)

        mount.do_mount(devpath, mountpoint, fstype)

        return mountpoint

    def unmount(self, docker_volume_name):
        return

    def check_exist(self, docker_volume_name):
        _, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} with state "
                     "{1}").format(docker_volume_name, state))

        if state == UNKNOWN:
            return False
        return True
