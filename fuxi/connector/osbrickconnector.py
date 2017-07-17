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

from os_brick.initiator import connector
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from cinderclient import exceptions as cinder_exception
from manilaclient.common.apiclient import exceptions as manila_exception

from fuxi.common import constants as consts
from fuxi.common import mount
from fuxi.common import state_monitor
from fuxi.connector import connector as fuxi_connector
from fuxi import exceptions
from fuxi import utils

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


def brick_get_connector_properties(multipath=False, enforce_multipath=False):
    """Wrapper to automatically set root_helper in brick calls.

    :param multipath: A boolean indicating whether the connector can
                      support multipath.
    :param enforce_multipath: If True, it raises exception when multipath=True
                              is specified but multipathd is not running.
                              If False, it falls back to multipath=False
                              when multipathd is not running.
    """

    root_helper = utils.get_root_helper()
    return connector.get_connector_properties(root_helper,
                                              CONF.my_ip,
                                              multipath,
                                              enforce_multipath)


def brick_get_connector(protocol, driver=None,
                        use_multipath=False,
                        device_scan_attempts=3,
                        *args, **kwargs):
    """Wrapper to get a brick connector object.

    This automatically populates the required protocol as well
    as the root_helper needed to execute commands.
    """

    root_helper = utils.get_root_helper()
    if protocol.upper() == "RBD":
        kwargs['do_local_attach'] = True
    return connector.InitiatorConnector.factory(
        protocol, root_helper,
        driver=driver,
        use_multipath=use_multipath,
        device_scan_attempts=device_scan_attempts,
        *args, **kwargs)


class CinderConnector(fuxi_connector.Connector):
    def __init__(self):
        super(CinderConnector, self).__init__()
        self.cinderclient = utils.get_cinderclient()

    def _get_connection_info(self, volume_id):
        LOG.info("Get connection info for osbrick connector and use it to "
                 "connect to volume")
        try:
            conn_info = self.cinderclient.volumes.initialize_connection(
                volume_id,
                brick_get_connector_properties())
            LOG.info("Get connection information %s", conn_info)
            return conn_info
        except cinder_exception.ClientException as e:
            LOG.error("Error happened when initialize connection"
                      " for volume. Error: %s", e)
            raise

    def _connect_volume(self, volume):
        conn_info = self._get_connection_info(volume.id)

        protocol = conn_info['driver_volume_type']
        brick_connector = brick_get_connector(protocol)
        device_info = brick_connector.connect_volume(conn_info['data'])
        LOG.info("Get device_info after connect to "
                 "volume %s", device_info)
        try:
            link_path = os.path.join(consts.VOLUME_LINK_DIR, volume.id)
            utils.execute('ln', '-s', os.path.realpath(device_info['path']),
                          link_path,
                          run_as_root=True)
        except processutils.ProcessExecutionError as e:
            LOG.error("Failed to create link for device. %s", e)
            raise
        return {'path': link_path}

    def _disconnect_volume(self, volume):
        try:
            link_path = self.get_device_path(volume)
            utils.execute('rm', '-f', link_path, run_as_root=True)
        except processutils.ProcessExecutionError as e:
            LOG.warning("Error happened when remove docker volume"
                        " mountpoint directory. Error: %s", e)

        conn_info = self._get_connection_info(volume.id)

        protocol = conn_info['driver_volume_type']
        brick_get_connector(protocol).disconnect_volume(conn_info['data'],
                                                        None)

    def connect_volume(self, volume, **connect_opts):
        mountpoint = connect_opts.get('mountpoint', None)
        host_name = utils.get_hostname()

        try:
            self.cinderclient.volumes.reserve(volume)
        except cinder_exception.ClientException:
            LOG.error("Reserve volume %s failed", volume)
            raise

        try:
            device_info = self._connect_volume(volume)
            self.cinderclient.volumes.attach(volume=volume,
                                             instance_uuid=None,
                                             mountpoint=mountpoint,
                                             host_name=host_name)
            LOG.info("Attach volume to this server successfully")
        except Exception:
            LOG.error("Attach volume %s to this server failed", volume)
            with excutils.save_and_reraise_exception():
                try:
                    self._disconnect_volume(volume)
                except Exception:
                    pass
                self.cinderclient.volumes.unreserve(volume)

        return device_info

    def disconnect_volume(self, volume, **disconnect_opts):
        self._disconnect_volume(volume)

        attachments = volume.attachments
        attachment_uuid = None
        for am in attachments:
            if am['host_name'].lower() == utils.get_hostname().lower():
                attachment_uuid = am['attachment_id']
                break
        try:
            self.cinderclient.volumes.detach(volume.id,
                                             attachment_uuid=attachment_uuid)
            LOG.info("Disconnect volume successfully")
        except cinder_exception.ClientException as e:
            LOG.error("Error happened when detach volume %(vol)s from this"
                      " server. Error: %(err)s",
                      {'vol': volume, 'err': e})
            raise

    def get_device_path(self, volume):
        return os.path.join(consts.VOLUME_LINK_DIR, volume.id)


SHARE_PROTO = (NFS, GLUSTERFS) = ('NFS', 'GLUSTERFS')
SHARE_ACCESS_TYPE = (IP, CERT) = ('ip', 'cert')
# PROTO_ACCESS_TYPE_MAP
# key: share protocol
# value: possible supported access type
PROTO_ACCESS_TYPE_MAP = {
    NFS: (IP,),
    GLUSTERFS: (CERT,)
}


class ManilaConnector(fuxi_connector.Connector):
    """Manager share access and mount.

    share access: ManilaConnector only support one access_type for
    each share_proto that Fuxi implements. The constant
    PROTO_ACCESS_TYPE_MAP record the supported share_proto and related
    possible supported access_type. Particularly, we use the first access_type
    as default when there are more than one access_type for share_proto, of
    course, we could set this in config file with
    conf.manila.proto_access_type_map
    """
    def __init__(self, manilaclient=None):
        super(ManilaConnector, self).__init__()
        if not manilaclient:
            manilaclient = utils.get_manilaclient()
        self.manilaclient = manilaclient
        self._set_proto_access_type_map()

    def _set_proto_access_type_map(self):
        conf_proto_at_map = CONF.manila.proto_access_type_map
        conf_proto_at_map = dict((k.upper(), v.lower())
                                 for k, v in conf_proto_at_map.items())
        unable_proto = [k for k in conf_proto_at_map.keys()
                        if k not in PROTO_ACCESS_TYPE_MAP.keys()]
        if unable_proto:
            raise exceptions.InvalidProtocol(
                "Find temporary unable share protocol {0}"
                .format(unable_proto))

        self.proto_access_type_map = dict()
        for key, value in PROTO_ACCESS_TYPE_MAP.items():
            if key in conf_proto_at_map:
                if conf_proto_at_map[key] in value:
                    self.proto_access_type_map[key] = conf_proto_at_map[key]
                else:
                    raise exceptions.InvalidAccessType(
                        "Access type {0} is not enabled for share "
                        "protocol {1}, please chose from {2}"
                        .format(conf_proto_at_map[key],
                                key,
                                PROTO_ACCESS_TYPE_MAP[key]))
            else:
                self.proto_access_type_map[key] = value[0]

    def _get_brick_connector(self, share):
        protocol = share.share_proto
        mount_point_base = os.path.join(CONF.volume_dir, 'manila')
        conn = {'mount_point_base': mount_point_base}
        return brick_get_connector(protocol, conn=conn)

    def _get_access_to(self, access_type):
        if access_type == IP:
            access_to = CONF.my_ip
            if not access_to:
                raise exceptions.InvalidAccessTo(
                    "The my_ip could not be None")
            return access_to
        elif access_type == CERT:
            access_to = CONF.manila.access_to_for_cert
            if not access_to:
                raise exceptions.InvalidAccessTo(
                    "The access_to_for_cert could not be None")
            return CONF.manila.access_to_for_cert
        raise exceptions.InvalidAccessType(
            "The access type %s is not enabled" % access_type)

    @utils.wrap_check_authorized
    def check_access_allowed(self, share):
        access_type = self.proto_access_type_map.get(share.share_proto, None)
        if not access_type:
            LOG.warning("The share_proto %s is not enabled currently",
                        share.share_proto)
            return False

        share_access_list = self.manilaclient.shares.access_list(share)
        for access in share_access_list:
            try:
                if self._get_access_to(access_type) == access.access_to \
                        and access.state == 'active':
                    return True
            except (exceptions.InvalidAccessType, exceptions.InvalidAccessTo):
                pass
        return False

    def _access_allow(self, share):
        share_proto = share.share_proto
        if share_proto not in self.proto_access_type_map.keys():
            raise exceptions.InvalidProtocol(
                "Not enabled share protocol %s" % share_proto)

        try:
            if self.check_access_allowed(share):
                return

            access_type = self.proto_access_type_map[share_proto]
            access_to = self._get_access_to(access_type)
            LOG.info("Allow machine to access share %(shr)s with "
                     "access_type %(type)s and access_to %(to)s",
                     {'shr': share, 'type': access_type, 'to': access_to})
            self.manilaclient.shares.allow(share, access_type, access_to, 'rw')
        except manila_exception.ClientException as e:
            LOG.error("Failed to grant access for server, %s", e)
            raise

        LOG.info("Waiting share %s access to be active", share)
        state_monitor.StateMonitor(
            self.manilaclient, share,
            'active',
            ('new',)).monitor_share_access(access_type, access_to)

    @utils.wrap_check_authorized
    def connect_volume(self, share, **connect_opts):
        self._access_allow(share)

        conn_prop = {
            'export': self.get_device_path(share),
            'name': share.share_proto
        }
        path_info = self._get_brick_connector(share).connect_volume(conn_prop)
        LOG.info("Connect share %(s)s successfully, path_info %(pi)s",
                 {'s': share, 'pi': path_info})
        return {'path': share.export_location}

    def _access_deny(self, share):
        try:
            share_access_list = self.manilaclient.shares.access_list(share)
            share_proto = share.share_proto
            access_type = self.proto_access_type_map.get(share_proto)
            access_to = self._get_access_to(access_type)
            for share_access in share_access_list:
                if share_access.access_type == access_type \
                        and share_access.access_to == access_to:
                    self.manilaclient.shares.deny(share, share_access.id)
                    break
        except manila_exception.ClientException as e:
            LOG.error("Error happened when revoking access for share "
                      "%(s)s. Error: %(err)s", {'s': share, 'err': e})
            raise

    @utils.wrap_check_authorized
    def disconnect_volume(self, share, **disconnect_opts):
        mountpoint = self.get_mountpoint(share)
        mount.Mounter().unmount(mountpoint)

        self._access_deny(share)

        def _check_access_binded(s):
            sal = self.manilaclient.shares.access_list(s)
            share_proto = s.share_proto
            access_type = self.proto_access_type_map.get(share_proto)
            access_to = self._get_access_to(access_type)
            for a in sal:
                if a.access_type == access_type and a.access_to == access_to:
                    if a.state in ('error', 'error_deleting'):
                        raise exceptions.NotMatchedState(
                            "Revoke access {0} failed".format(a))
                    return True
            return False

        start_time = time.time()
        while time.time() - start_time < consts.ACCSS_DENY_TIMEOUT:
            if not _check_access_binded(share):
                LOG.info("Disconnect share %s successfully", share)
                return
            time.sleep(consts.SCAN_INTERVAL)

        raise exceptions.TimeoutException("Disconnect volume timeout")

    def get_device_path(self, share):
        return share.export_location

    def set_client(self):
        self.manilaclient = utils.get_manilaclient()

    @utils.wrap_check_authorized
    def get_mountpoint(self, share):
        if not self.check_access_allowed(share):
            return ''

        conn_prop = {
            'export': self.get_device_path(share),
            'name': share.share_proto
        }
        brick_connector = self._get_brick_connector(share)
        volume_paths = brick_connector.get_volume_paths(conn_prop)
        return volume_paths[0].rsplit('/', 1)[0]
