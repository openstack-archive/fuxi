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

import collections
import flask
import os

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log
from oslo_utils import importutils

from fuxi import app
from fuxi import exceptions
from fuxi.i18n import _
from fuxi import utils

CONF = cfg.CONF

LOG = log.getLogger(__name__)

CINDER = 'cinder'
MANILA = 'manila'

volume_providers_conf = {
    CINDER: 'fuxi.volumeprovider.cinder.Cinder',
    MANILA: 'fuxi.volumeprovider.manila.Manila', }


def init_app_conf():
    # Init volume providers.
    volume_providers = CONF.volume_providers
    if not volume_providers:
        raise Exception(_("Must define volume providers in "
                          "configuration file"))

    app.volume_providers = collections.OrderedDict()
    for provider in volume_providers:
        if provider in volume_providers_conf:
            app.volume_providers[provider] = importutils\
                .import_class(volume_providers_conf[provider])()
            LOG.info("Load volume provider: %s", provider)
        else:
            LOG.warning("Could not find volume provider: %s", provider)
    if not app.volume_providers:
        raise Exception(_("Not provide at least one effective "
                          "volume provider"))

    # Init volume store directory.
    try:
        volume_dir = CONF.volume_dir
        if not os.path.exists(volume_dir) or not os.path.isdir(volume_dir):
            utils.execute('mkdir', '-p', '-m=700', volume_dir,
                          run_as_root=True)
    except processutils.ProcessExecutionError:
        raise


def get_docker_volume(docker_volume_name):
    for provider in app.volume_providers.values():
        try:
            return provider.show(docker_volume_name)
        except exceptions.NotFound:
            pass
    return None


@app.route('/Plugin.Activate', methods=['POST'])
def plugin_activate():
    LOG.info("/Plugin.Activate")
    return flask.jsonify(Implements=[u'VolumeDriver'])


@app.route('/VolumeDriver.Create', methods=['POST'])
def volumedriver_create():
    json_data = flask.request.get_json(force=True)
    LOG.info("Received JSON data %s for /VolumeDriver.Create", json_data)

    docker_volume_name = json_data.get('Name', None)
    volume_opts = json_data.get('Opts', None) or {}
    if not docker_volume_name:
        msg = _("Request /VolumeDriver.Create need parameter 'Name'")
        LOG.error(msg)
        raise exceptions.InvalidInput(msg)
    if not isinstance(volume_opts, dict):
        msg = _("Request parameter 'Opts' must be dict type")
        LOG.error(msg)
        raise exceptions.InvalidInput(msg)

    volume_provider_type = volume_opts.get('volume_provider', None)
    if not volume_provider_type:
        volume_provider_type = list(app.volume_providers.keys())[0]

    if volume_provider_type not in app.volume_providers:
        msg_fmt = _("Could not find a handler for %(volume_provider_type)s "
                    "volume") % {'volume_provider_type': volume_provider_type}
        LOG.error(msg_fmt)
        return flask.jsonify(Err=msg_fmt)

    # If the volume with the same name already exists in other volume
    # provider backend, then raise an error
    for vpt, provider in app.volume_providers.items():
        if volume_provider_type != vpt \
                and provider.check_exist(docker_volume_name):
            msg_fmt = _("The volume with the same name already exists in "
                        "other volume provider backend")
            LOG.error(msg_fmt)
            return flask.jsonify(Err=msg_fmt)

    # Create if volume does not exist, or attach to this server if needed
    # volume exists in related volume provider.
    app.volume_providers[volume_provider_type].create(docker_volume_name,
                                                      volume_opts)

    return flask.jsonify(Err=u'')


@app.route('/VolumeDriver.Remove', methods=['POST'])
def volumedriver_remove():
    json_data = flask.request.get_json(force=True)
    LOG.info("Received JSON data %s for /VolumeDriver.Remove", json_data)

    docker_volume_name = json_data.get('Name', None)
    if not docker_volume_name:
        msg = _("Request /VolumeDriver.Remove need parameter 'Name'")
        LOG.error(msg)
        raise exceptions.InvalidInput(msg)

    for provider in app.volume_providers.values():
        if provider.delete(docker_volume_name):
            return flask.jsonify(Err=u'')

    return flask.jsonify(Err=u'')


@app.route('/VolumeDriver.Mount', methods=['POST'])
def volumedriver_mount():
    json_data = flask.request.get_json(force=True)
    LOG.info("Receive JSON data %s for /VolumeDriver.Mount", json_data)

    docker_volume_name = json_data.get('Name', None)
    if not docker_volume_name:
        msg = _("Request /VolumeDriver.Mount need parameter 'Name'")
        LOG.error(msg)
        raise exceptions.InvalidInput(msg)

    for provider in app.volume_providers.values():
        if provider.check_exist(docker_volume_name):
            mountpoint = provider.mount(docker_volume_name)
            return flask.jsonify(Mountpoint=mountpoint, Err=u'')

    return flask.jsonify(Err=u'Mount Failed')


@app.route('/VolumeDriver.Path', methods=['POST'])
def volumedriver_path():
    json_data = flask.request.get_json(force=True)
    LOG.info("Receive JSON data %s for /VolumeDriver.Path", json_data)

    docker_volume_name = json_data.get('Name', None)
    if not docker_volume_name:
        msg = _("Request /VolumeDriver.Path need parameter 'Name'")
        LOG.error(msg)
        raise exceptions.InvalidInput(msg)

    volume = get_docker_volume(docker_volume_name)
    if volume is not None:
        mountpoint = volume.get('Mountpoint', '')
        LOG.info("Get mountpoint %(mp)s for docker volume %(name)s",
                 {'mp': mountpoint, 'name': docker_volume_name})
        return flask.jsonify(Mountpoint=mountpoint, Err=u'')

    LOG.warning("Can't find mountpoint for docker volume %(name)s",
                {'name': docker_volume_name})
    return flask.jsonify(Err=u'Mountpoint Not Found')


@app.route('/VolumeDriver.Unmount', methods=['POST'])
def volumedriver_unmount():
    json_data = flask.request.get_json(force=True)
    LOG.info('Receive JSON data %s for VolumeDriver.Unmount', json_data)
    return flask.jsonify(Err=u'')


@app.route('/VolumeDriver.Get', methods=['POST'])
def volumedriver_get():
    json_data = flask.request.get_json(force=True)
    LOG.info("Receive JSON data %s for /VolumeDriver.Get", json_data)

    docker_volume_name = json_data.get('Name', None)
    if not docker_volume_name:
        msg = _("Request /VolumeDriver.Get need parameter 'Name'")
        LOG.error(msg)
        raise exceptions.InvalidInput(msg)

    volume = get_docker_volume(docker_volume_name)
    if volume is not None:
        LOG.info("Get docker volume: %s", volume)
        return flask.jsonify(Volume=volume, Err=u'')

    LOG.warning("Can't find volume %s from every provider",
                docker_volume_name)
    return flask.jsonify(Err=u'Volume Not Found')


@app.route('/VolumeDriver.List', methods=['POST'])
def volumedriver_list():
    LOG.info("/VolumeDriver.List")
    docker_volumes = []
    for provider in app.volume_providers.values():
        vs = provider.list()
        if vs:
            docker_volumes.extend(vs)

    LOG.info("Get volumes from volume providers. Volumes: %s",
             docker_volumes)
    return flask.jsonify(Err=u'', Volumes=docker_volumes)


@app.route('/VolumeDriver.Capabilities', methods=['POST'])
def volumedriver_capabilities():
    return flask.jsonify(Capabilities={'Scope': 'global'})
