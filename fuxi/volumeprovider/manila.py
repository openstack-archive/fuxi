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

"""
Volume Provider for OpenStack Manila.

Current supported and checked Manila share protocol(share driver)
NFS(Generic)
NFS(Glusterfs)
GLUSTERFS(GlusterfsNative)
"""

import time

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from manilaclient.common.apiclient import exceptions as manila_exception

from fuxi.common import constants as consts
from fuxi.common import state_monitor
from fuxi import exceptions
from fuxi.i18n import _
from fuxi import utils
from fuxi.volumeprovider import provider

CONF = cfg.CONF
manila_conf = CONF.manila

NOT_ATTACH = consts.NOT_ATTACH
ATTACH_TO_THIS = consts.ATTACH_TO_THIS

OSBRICK = 'osbrick'

volume_connector_conf = {
    OSBRICK: 'fuxi.connector.osbrickconnector.ManilaConnector'}

LOG = logging.getLogger(__name__)


def extract_share_kwargs(docker_volume_name, docker_volume_opts):
    """Extract parameters for creating manila share.

    Retrieve required parameters and remove unsupported arguments from
    client input. These parameters are used to create a Cinder volume.

    :param docker_volume_name: Name for Manila share.
    :param docker_volume_opts: Optional parameters for Manila share.
    :rtype: dict
    """
    options = ['share_proto', 'size', 'snapshot_id', 'description',
               'share_network', 'share_type', 'is_public',
               'availability_zone', 'consistency_group_id']

    kwargs = {}
    if 'size' in docker_volume_opts:
        try:
            size = int(docker_volume_opts.pop('size'))
        except ValueError:
            msg = _("Volume size must able to convert to int type")
            LOG.error(msg)
            raise exceptions.InvalidInput(msg)
    else:
        size = CONF.default_volume_size
        LOG.info("Volume size doesn't provide from command, so use "
                 "default size %sG", size)
    kwargs['size'] = size

    share_proto = docker_volume_opts.pop('share_proto', None) \
        or manila_conf.share_proto
    kwargs['share_proto'] = share_proto

    for key, value in docker_volume_opts.items():
        if key in options:
            kwargs[key] = value

    kwargs['name'] = docker_volume_name
    kwargs['metadata'] = {consts.VOLUME_FROM: CONF.volume_from}

    return kwargs


class Manila(provider.Provider):
    volume_provider_type = 'manila'

    def __init__(self):
        super(Manila, self).__init__()
        self.manilaclient = utils.get_manilaclient()

        conn_conf = manila_conf.volume_connector
        if not conn_conf or conn_conf not in volume_connector_conf:
            msg = _("Must provide a valid volume connector")
            LOG.error(msg)
            raise exceptions.InvalidInput(msg)
        self.connector = importutils.import_object(
            volume_connector_conf[conn_conf],
            manilaclient=self.manilaclient)

    def set_client(self):
        self.manilaclient = utils.get_manilaclient()

    def _get_docker_volume(self, docker_volume_name):
        search_opts = {'name': docker_volume_name,
                       'metadata': {consts.VOLUME_FROM: CONF.volume_from}}
        try:
            docker_shares = self.manilaclient.shares.list(
                search_opts=search_opts)
        except manila_exception.ClientException as e:
            LOG.error("Could not retrieve Manila share list. Error: %s", e)
            raise

        if not docker_shares:
            raise exceptions.NotFound("Could not find share with "
                                      "search_opts: {0}".format(search_opts))
        elif len(docker_shares) > 1:
            raise exceptions.TooManyResources(
                "Find too many shares with search_opts: {0}, while "
                "for Fuxi, should get only one share with provided "
                "search_opts".format(docker_shares))

        docker_share = docker_shares[0]
        if self.connector.check_access_allowed(docker_share):
            return docker_share, ATTACH_TO_THIS
        else:
            return docker_share, NOT_ATTACH

    def _create_share(self, docker_volume_name, share_opts):
        share_kwargs = extract_share_kwargs(docker_volume_name,
                                            share_opts)

        try:
            LOG.debug("Start to create share from Manila")
            share = self.manilaclient.shares.create(**share_kwargs)
        except manila_exception.ClientException as e:
            LOG.error("Create Manila share failed. Error: {0}", e)
            raise

        LOG.info("Waiting for share %s status to be available", share)
        share_monitor = state_monitor.StateMonitor(self.manilaclient,
                                                   share,
                                                   'available',
                                                   ('creating',))
        share = share_monitor.monitor_manila_share()
        LOG.info("Creating share %s successfully", share)
        return share

    def _create_from_existing_share(self, docker_volume_name,
                                    share_id, share_opts):
        try:
            share = self.manilaclient.shares.get(share_id)
        except manila_exception.NotFound:
            LOG.error("Could not find share %s", share_id)
            raise

        if share.status != 'available':
            raise exceptions.UnexpectedStateException(
                "Manila share is unavailable")

        if share.name != docker_volume_name:
            LOG.error("Provided volume name %(d_name)s does not match "
                      "with existing share name %(s_name)s",
                      {'d_name': docker_volume_name,
                       's_name': share.name})
            raise exceptions.InvalidInput('Volume name does not match')

        metadata = {consts.VOLUME_FROM: CONF.volume_from}
        self.manilaclient.shares.update_all_metadata(share, metadata)

        return share

    @utils.wrap_check_authorized
    def create(self, docker_volume_name, volume_opts):
        try:
            share, state = self._get_docker_volume(docker_volume_name)
            if share:
                LOG.warning("Volume %(vol)s already exists in Manila, and "
                            "the related Manila share is %(share)s",
                            {'vol': docker_volume_name, 'share': share})

                if state == NOT_ATTACH:
                    return self.connector.connect_volume(share)
                else:
                    return {'path': self.connector.get_device_path(share)}
        except exceptions.NotFound:
            pass

        if 'volume_id' in volume_opts:
            share = self._create_from_existing_share(
                docker_volume_name,
                volume_opts.pop('volume_id'),
                volume_opts)
        else:
            share = self._create_share(docker_volume_name, volume_opts)

        return self.connector.connect_volume(share)

    def _delete_share(self, share):
        try:
            share_access_list = self.manilaclient.shares.access_list(share)
            if len(share_access_list) > 0:
                LOG.warning("Share %s is still used by other server, so "
                            "should not delete it.", share)
                return

            self.manilaclient.shares.delete(share)
        except manila_exception.ClientException as e:
            LOG.error("Error happened when delete Volume %(vol)s (Manila "
                      "share: %(share)s). Error: %(err)s",
                      {'vol': share.name, 'share': share, 'err': e})
            raise

        start_time = time.time()
        while True:
            try:
                self.manilaclient.shares.get(share.id)
            except manila_exception.NotFound:
                break

            if time.time() - start_time > consts.DESTROY_SHARE_TIMEOUT:
                raise exceptions.TimeoutException

            time.sleep(consts.SHARE_SCAN_INTERVAL)

        LOG.debug("Delete share %s from Manila successfully", share)

    @utils.wrap_check_authorized
    def delete(self, docker_volume_name):
        try:
            share, state = self._get_docker_volume(docker_volume_name)
            if state == NOT_ATTACH:
                self._delete_share(share)
                return True
        except exceptions.NotFound:
            return False

        mountpoint = self.connector.get_mountpoint(share)
        self.connector.disconnect_volume(share)
        self._clear_mountpoint(mountpoint)

        self._delete_share(share)
        return True

    @utils.wrap_check_authorized
    def mount(self, docker_volume_name):
        share, state = self._get_docker_volume(docker_volume_name)
        if state == NOT_ATTACH:
            LOG.warning("Find share %s, but not attach to this server, "
                        "so connect it", share)
            self.connector.connect_volume(share)

        mountpoint = self.connector.get_mountpoint(share)
        if not mountpoint:
            self.connector.connect_volume(share)
        return mountpoint

    def unmount(self, docker_volume_name):
        return

    @utils.wrap_check_authorized
    def show(self, docker_volume_name):
        share, state = self._get_docker_volume(docker_volume_name)
        mountpoint = self.connector.get_mountpoint(share)
        return {'Name': docker_volume_name, 'Mountpoint': mountpoint}

    def _get_docker_volumes(self, search_opts=None):
        try:
            docker_shares = self.manilaclient.shares.list(
                search_opts=search_opts)
        except manila_exception.ClientException as e:
            LOG.error('Could not retrieve Manila shares. Error: %s', e)
            raise

        docker_volumes = []

        for share in docker_shares:
            docker_volumes.append(
                {'Name': share.name,
                 'Mountpoint': self.connector.get_mountpoint(share)})
        LOG.info("Retrieve docker volumes %s from Manila "
                 "successfully", docker_volumes)
        return docker_volumes

    @utils.wrap_check_authorized
    def list(self):
        search_opts = {'metadata': {consts.VOLUME_FROM: CONF.volume_from}}
        return self._get_docker_volumes(search_opts)

    @utils.wrap_check_authorized
    def check_exist(self, docker_volume_name):
        try:
            self._get_docker_volume(docker_volume_name)
        except exceptions.NotFound:
            return False
        return True
