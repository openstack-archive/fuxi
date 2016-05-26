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

from os_brick.initiator import connector
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging

from fuxi.common import consts
from fuxi.connector import connector as fuxi_connector
from fuxi.i18n import _LI, _LE
from fuxi import utils

from cinderclient import exceptions as cinder_exception

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
                        execute=processutils.execute,
                        use_multipath=False,
                        device_scan_attempts=3,
                        *args, **kwargs):
    """Wrapper to get a brick connector object.

    This automatically populates the required protocol as well
    as the root_helper needed to execute commands.
    """

    root_helper = utils.get_root_helper()
    return connector.InitiatorConnector.factory(
        protocol, root_helper,
        driver=driver,
        execute=execute,
        use_multipath=use_multipath,
        device_scan_attempts=device_scan_attempts,
        *args, **kwargs)


class CinderConnector(fuxi_connector.Connector):
    protocol = CONF.cinder.protocol

    def __init__(self):
        super(CinderConnector, self).__init__()
        self.connector_properties = brick_get_connector_properties()
        self.osbrickconnector = brick_get_connector(self.protocol)
        self.cinderclient = utils.get_cinderclient()

    def connect_volume(self, volume, **connect_opts):
        mountpoint = connect_opts.get('mountpoint', None)
        host_name = utils.get_hostname()

        try:
            LOG.info(_LI("Attach volume {0} to this server.").format(volume))
            self.cinderclient.volumes.attach(volume=volume,
                                             instance_uuid=None,
                                             mountpoint=mountpoint,
                                             host_name=host_name)
            LOG.info(_LI("Attach volume to this server successfully."))
        except cinder_exception.ClientException as e:
            msg = _LE("Error happened when attach volume {0} to this server. "
                      "Error: {1}").format(volume, e)
            LOG.error(msg)
            raise

        return self._connect_volume(volume)

    def _connect_volume(self, volume):
        conn_info = self._get_connection_info(volume.id)

        try:
            device_info = self.osbrickconnector.connect_volume(
                conn_info['data'])
            LOG.info(_LI("Get device_info after connect to "
                         "volume %s") % device_info)

            link_path = os.path.join(consts.VOLUME_LINK_DIR, volume.id)
            utils.psutil_execute('ln', '-s',
                                 os.path.realpath(device_info['path']),
                                 link_path,
                                 run_as_root=True)

            return {'path': link_path, 'iscsi_path': device_info['path']}
        except processutils.ProcessExecutionError as e:
            LOG.error(_LE("Error happened when connecting to iSCSI "
                          "target. {0}").format(e))
            raise

    def disconnect_volume(self, volume, **disconnect_opts):
        conn_info = self._get_connection_info(volume.id)
        try:
            self.osbrickconnector.disconnect_volume(conn_info['data'], None)
        except processutils.ProcessExecutionError as e:
            msg = _LE("Error happened when disconnect volume {0} {1} from "
                      "this server. Error: {2}").format(volume.name, volume, e)
            LOG.error(msg)
            raise

        attachments = volume.attachments
        attachment_uuid = None
        for am in attachments:
            if am['host_name'] == utils.get_hostname():
                attachment_uuid = am['attachment_id']
                break
        try:
            self.cinderclient.volumes.detach(volume.id,
                                             attachment_uuid=attachment_uuid)
            LOG.info(_LI("disconnect volume successfully."))
        except cinder_exception.ClientException as e:
            msg = _LE("Error happened when detach volume {0} {1} from this "
                      "server. Error: {2}").format(volume.name, volume, e)
            LOG.error(msg)
            raise

    def _get_connection_info(self, volume_id):
        LOG.info(_LI("Get connection info for osbrick connector and use it to "
                     "connect to volume."))
        try:
            conn_info = self.cinderclient.volumes.initialize_connection(
                volume_id,
                self.connector_properties)
            msg = _LI("Get connection information {0}").format(conn_info)
            LOG.info(msg)
            return conn_info
        except cinder_exception.ClientException as e:
            msg = _LE("Error happened when initialize connection for volume. "
                      "Error: {0}.").format(e)
            LOG.error(msg)
            raise

    def get_device_path(self, volume):
        return os.path.join(consts.VOLUME_LINK_DIR, volume.id)
