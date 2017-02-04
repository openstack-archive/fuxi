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
cinder_conf = CONF.cinder

# Volume states
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
            msg = _LE("Volume size must be able to convert to int type")
            LOG.error(msg)
            raise exceptions.InvalidInput(msg)
    else:
        size = CONF.default_volume_size
        LOG.info(_LI("Volume size doesn't provide from command, so use"
                     " default size %sG"), size)
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
    """Get a value that could represent this server."""
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
        connector = cinder_conf.volume_connector
        if not connector or connector not in volume_connector_conf:
            msg = _LE("Must provide an valid volume connector")
            LOG.error(msg)
            raise exceptions.FuxiException(msg)
        return importutils.import_class(volume_connector_conf[connector])()

    def _get_docker_volume(self, docker_volume_name):
        try:
            search_opts = {'name': docker_volume_name,
                           'metadata': {consts.VOLUME_FROM: CONF.volume_from}}
            vols = self.cinderclient.volumes.list(search_opts=search_opts)
        except cinder_exception.ClientException as ex:
            LOG.error(_LE("Error happened while getting volume list "
                          "information from Cinder. Error: %s"), ex)
            raise

        vol_num = len(vols)
        if vol_num == 1:
            docker_volume = vols[0]
            if docker_volume.attachments:
                volume_connector = cinder_conf.volume_connector
                host_id = get_host_id()
                for am in docker_volume.attachments:
                    if volume_connector == OPENSTACK:
                        if am['server_id'] == host_id:
                            return docker_volume, ATTACH_TO_THIS
                    elif volume_connector == OSBRICK:
                        if (am['host_name'] or '').lower() == host_id:
                            return docker_volume, ATTACH_TO_THIS
                return docker_volume, ATTACH_TO_OTHER
            else:
                return docker_volume, NOT_ATTACH
        elif vol_num == 0:
            return None, UNKNOWN
        else:
            raise exceptions.TooManyResources(
                "find too many volumes with search_opts=%s" % search_opts)

    def _check_attached_to_this(self, cinder_volume):
        host_id = get_host_id()
        vol_conn = cinder_conf.volume_connector
        for am in cinder_volume.attachments:
            if vol_conn == OPENSTACK and am['server_id'] == host_id:
                return True
            elif vol_conn == OSBRICK and am['host_name'] \
                    and am['host_name'].lower() == host_id:
                return True
        return False

    def _create_volume(self, docker_volume_name, volume_opts):
        LOG.info(_LI("Start to create docker volume %s from Cinder"),
                 docker_volume_name)

        cinder_volume_kwargs = get_cinder_volume_kwargs(docker_volume_name,
                                                        volume_opts)

        try:
            volume = self.cinderclient.volumes.create(**cinder_volume_kwargs)
        except cinder_exception.ClientException as e:
            LOG.error(_LE("Error happened when create an volume %(vol)s from"
                          " Cinder. Error: %(err)s"),
                      {'vol': docker_volume_name, 'err': e})
            raise

        LOG.info(_LI("Waiting volume %s to be available"), volume)
        volume_monitor = state_monitor.StateMonitor(
            self.cinderclient,
            volume,
            'available',
            ('creating',),
            time_delay=consts.VOLUME_SCAN_TIME_DELAY)
        volume = volume_monitor.monitor_cinder_volume()

        LOG.info(_LI("Create docker volume %(d_v)s %(vols) from Cinder "
                     "successfully"),
                 {'d_v': docker_volume_name, 'vol': volume})
        return volume

    def _create_from_existing_volume(self, docker_volume_name,
                                     cinder_volume_id,
                                     volume_opts):
        try:
            cinder_volume = self.cinderclient.volumes.get(cinder_volume_id)
        except cinder_exception.ClientException as e:
            msg = _LE("Failed to get volume %(vol_id)s from Cinder. "
                      "Error: %(err)s")
            LOG.error(msg, {'vol_id': cinder_volume_id, 'err': e})
            raise

        status = cinder_volume.status
        if status not in ('available', 'in-use'):
            LOG.error(_LE("Current volume %(vol)s status %(status)s not in "
                          "desired states"),
                      {'vol': cinder_volume, 'status': status})
            raise exceptions.NotMatchedState('Cinder volume is unavailable')
        elif status == 'in-use' and not cinder_volume.multiattach:
            if not self._check_attached_to_this(cinder_volume):
                msg = _LE("Current volume %(vol)s status %(status)s not "
                          "in desired states")
                LOG.error(msg, {'vol': cinder_volume, 'status': status})
                raise exceptions.NotMatchedState(
                    'Cinder volume is unavailable')

        if cinder_volume.name != docker_volume_name:
            LOG.error(_LE("Provided volume name %(d_name)s does not match "
                          "with existing Cinder volume name %(c_name)s"),
                      {'d_name': docker_volume_name,
                       'c_name': cinder_volume.name})
            raise exceptions.InvalidInput('Volume name does not match')

        fstype = volume_opts.pop('fstype', cinder_conf.fstype)
        vol_fstype = cinder_volume.metadata.get('fstype',
                                                cinder_conf.fstype)
        if fstype != vol_fstype:
            LOG.error(_LE("Volume already exists with fstype %(c_fstype)s, "
                          "but currently provided fstype is %(fstype)s, not "
                          "match"), {'c_fstype': vol_fstype, 'fstype': fstype})
            raise exceptions.InvalidInput('FSType does not match')

        try:
            metadata = {consts.VOLUME_FROM: CONF.volume_from,
                        'fstype': fstype}
            self.cinderclient.volumes.set_metadata(cinder_volume, metadata)
        except cinder_exception.ClientException as e:
            LOG.error(_LE("Failed to update volume %(vol)s information. "
                          "Error: %(err)s"),
                      {'vol': cinder_volume_id, 'err': e})
            raise
        return cinder_volume

    def create(self, docker_volume_name, volume_opts):
        if not volume_opts:
            volume_opts = {}

        connector = self._get_connector()
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume {0} {1} with state "
                     "{2}").format(docker_volume_name, cinder_volume, state))

        device_info = {}
        if state == ATTACH_TO_THIS:
            LOG.warning(_LW("The volume {0} {1} already exists and attached "
                            "to this server").format(docker_volume_name,
                                                     cinder_volume))
            device_info = {'path': connector.get_device_path(cinder_volume)}
        elif state == NOT_ATTACH:
            LOG.warning(_LW("The volume {0} {1} is already exists but not "
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
            if 'volume_id' in volume_opts:
                cinder_volume = self._create_from_existing_volume(
                    docker_volume_name,
                    volume_opts.pop('volume_id'),
                    volume_opts)
                if self._check_attached_to_this(cinder_volume):
                    device_info = {
                        'path': connector.get_device_path(cinder_volume)}
                else:
                    device_info = connector.connect_volume(cinder_volume)
            else:
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
            LOG.error(_LE("Error happened when delete volume from Cinder."
                          " Error: %s"), e)
            raise

        start_time = time.time()
        # Wait until the volume is not there or until the operation timeout
        while (time.time() - start_time < consts.DESTROY_VOLUME_TIMEOUT):
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
        LOG.info(_LI("Get docker volume %(d_v)s %(vol)s with state %(st)s"),
                 {'d_v': docker_volume_name, 'vol':  cinder_volume,
                  'st': state})

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

            mounter = mount.Mounter()
            mps = mounter.get_mps_by_device(devpath)
            ref_count = len(mps)
            if ref_count > 0:
                mountpoint = self._get_mountpoint(docker_volume_name)
                if mountpoint in mps:
                    mounter.unmount(mountpoint)

                    self._clear_mountpoint(mountpoint)

                    # If this volume is still mounted on other mount point,
                    # then return.
                    if ref_count > 1:
                        return True
                else:
                    return True

            # Detach device from this server.
            self._get_connector().disconnect_volume(cinder_volume)

            available_volume = self.cinderclient.volumes.get(cinder_volume.id)
            # If this volume is not used by other server any more,
            # than delete it from Cinder.
            if not available_volume.attachments:
                LOG.warning(
                    _LW("No other servers still use this volume %(d_v)s"
                        " %(vol)s any more, so delete it from Cinder"),
                    {'d_v': docker_volume_name, 'vol': cinder_volume})
                self._delete_volume(available_volume)
            return True
        elif state == NOT_ATTACH:
            self._delete_volume(cinder_volume)
            return True
        elif state == ATTACH_TO_OTHER:
            msg = _LW("Volume %s is still in use, could not delete it")
            LOG.warning(msg, cinder_volume)
            return True
        elif state == UNKNOWN:
            return False
        else:
            msg = _LE("Volume %(vol_name)s %(c_vol)s "
                      "state %(state)s is invalid")
            LOG.error(msg, {'vol_name': docker_volume_name,
                            'c_vol': cinder_volume,
                            'state': state})
            raise exceptions.NotMatchedState()

    def list(self):
        LOG.info(_LI("Start to retrieve all docker volumes from Cinder"))

        docker_volumes = []
        try:
            search_opts = {'metadata': {consts.VOLUME_FROM: CONF.volume_from}}
            for vol in self.cinderclient.volumes.list(search_opts=search_opts):
                docker_volume_name = vol.name
                if not docker_volume_name:
                    continue

                mountpoint = self._get_mountpoint(vol.name)
                devpath = os.path.realpath(
                    self._get_connector().get_device_path(vol))
                mps = mount.Mounter().get_mps_by_device(devpath)
                mountpoint = mountpoint if mountpoint in mps else ''
                docker_vol = {'Name': docker_volume_name,
                              'Mountpoint': mountpoint}
                docker_volumes.append(docker_vol)
        except cinder_exception.ClientException as e:
            LOG.error(_LE("Retrieve volume list failed. Error: %s"), e)
            raise

        LOG.info(_LI("Retrieve docker volumes %s from Cinder "
                     "successfully"), docker_volumes)
        return docker_volumes

    def show(self, docker_volume_name):
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume %s(d_v)s %(vol)s with state %(st)s"),
                 {'d_v': docker_volume_name, 'vol': cinder_volume,
                  'st': state})

        if state == ATTACH_TO_THIS:
            devpath = os.path.realpath(
                self._get_connector().get_device_path(cinder_volume))
            mp = self._get_mountpoint(docker_volume_name)
            LOG.info(
                _LI("Expected devpath: %(dp)s and mountpoint: %(mp)s for"
                    " volume: %(d_v)s %(vol)s"),
                {'dp': devpath, 'mp': mp,
                 'd_v': docker_volume_name, 'vol': cinder_volume})
            mounter = mount.Mounter()
            return {"Name": docker_volume_name,
                    "Mountpoint": mp if mp in mounter.get_mps_by_device(
                        devpath) else ''}
        elif state in (NOT_ATTACH, ATTACH_TO_OTHER):
            return {'Name': docker_volume_name, 'Mountpoint': ''}
        elif state == UNKNOWN:
            msg = _LW("Can't find this volume '{0}' in "
                      "Cinder").format(docker_volume_name)
            LOG.warning(msg)
            raise exceptions.NotFound(msg)
        else:
            msg = _LE("Volume '{0}' exists, but not attached to this volume,"
                      "and current state is {1}").format(docker_volume_name,
                                                         state)
            raise exceptions.NotMatchedState(msg)

    def mount(self, docker_volume_name):
        cinder_volume, state = self._get_docker_volume(docker_volume_name)
        LOG.info(_LI("Get docker volume %s(d_v)s %(vol)s with state %(st)s"),
                 {'d_v': docker_volume_name, 'vol': cinder_volume,
                  'st': state})

        connector = self._get_connector()
        if state == NOT_ATTACH:
            connector.connect_volume(cinder_volume)
        elif state == ATTACH_TO_OTHER:
            if cinder_volume.multiattach:
                connector.connect_volume(cinder_volume)
            else:
                msg = _("Volume {0} {1} is not shareable").format(
                    docker_volume_name, cinder_volume)
                raise exceptions.FuxiException(msg)
        elif state != ATTACH_TO_THIS:
            msg = _("Volume %(vol_name)s %(c_vol)s is not in correct state, "
                    "current state is %(state)s")
            LOG.error(msg, {'vol_name': docker_volume_name,
                            'c_vol': cinder_volume,
                            'state': state})
            raise exceptions.NotMatchedState()

        link_path = connector.get_device_path(cinder_volume)
        if not os.path.exists(link_path):
            LOG.warning(_LW("Could not find device link file, "
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
        LOG.info(_LI("Get docker volume %s(d_v)s with state %(st)s"),
                 {'d_v': docker_volume_name, 'st': state})

        if state == UNKNOWN:
            return False
        return True
