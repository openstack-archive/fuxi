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

import flask
import os
import requests
import socket
import sys
import traceback

from fuxi.common import consts
from fuxi import exceptions
from fuxi.i18n import _LE

from cinderclient import client as cinder_client
from cinderclient import exceptions as cinder_exception
from keystoneclient.auth import get_plugin_class
from keystoneclient.session import Session
from novaclient import client as nova_client
from novaclient import exceptions as nova_exception
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils
from oslo_utils import uuidutils
from werkzeug import exceptions as w_exceptions

cloud_init_conf = '/var/lib/cloud/instances'

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


def get_hostname():
    return socket.gethostname()


def get_instance_uuid():
    try:
        dirs = os.listdir(cloud_init_conf)
        for uuid_dir in dirs:
            if uuidutils.is_uuid_like(uuid_dir):
                return uuid_dir
    except Exception as e:
        LOG.error(_LE("Get instance_uuid from cloud-init failed."))

    try:
        resp = requests.get('http://169.254.169.254/openstack',
                            timeout=consts.CURL_MD_TIMEOUT)
        metadata_api_versions = resp.text.split()
        metadata_api_versions.sort(reverse=True)
    except Exception as e:
        LOG.error(_LE("Get metadata apis failed. Error: {}").format(e))
        raise exceptions.FuxiException("Metadata API Not Found")

    for api_version in metadata_api_versions:
        metadata_url = ''.join(['http://169.254.169.254/openstack/',
                                api_version,
                                '/meta_data.json'])
        try:
            resp = requests.get(metadata_url,
                                timeout=consts.CURL_MD_TIMEOUT)
            metadata = resp.json()
            if metadata.get('uuid', None):
                return metadata['uuid']
        except Exception as e:
            msg = _LE("Get instance_uuid from metadata server {} "
                      "failed. Error: {}").format(metadata_url, e)
            LOG.error(msg)
            continue

    raise exceptions.FuxiException("Instance UUID NOT FOUND")


# Return all errors as JSON. From http://flask.pocoo.org/snippets/83/
def make_json_app(import_name, **kwargs):
    app = flask.Flask(import_name, **kwargs)

    @app.errorhandler(exceptions.FuxiException)
    @app.errorhandler(cinder_exception.ClientException)
    @app.errorhandler(nova_exception.ClientException)
    @app.errorhandler(processutils.ProcessExecutionError)
    def make_json_error(ex):
        traceback.print_exc(file=sys.stderr)
        response = flask.jsonify({"Err": str(ex)})
        response.status_code = w_exceptions.InternalServerError.code
        if isinstance(ex, w_exceptions.HTTPException):
            response.status_code = ex.code
        content_type = 'application/vnd.docker.plugins.v1+json; charset=utf-8'
        response.headers['Content-Type'] = content_type
        return response

    for code in w_exceptions.default_exceptions:
        app.error_handler_spec[None][code] = make_json_error

    return app


def driver_dict_from_config(named_driver_config, *args, **kwargs):
    driver_registry = dict()

    for driver_str in named_driver_config:
        driver_type, _sep, driver = driver_str.partition('=')
        driver_class = importutils.import_class(driver)
        driver_registry[driver_type] = driver_class(*args, **kwargs)
    return driver_registry


def _openstack_auth_from_config(**config):
    plugin_class = get_plugin_class('password')
    plugin_options = plugin_class.get_options()
    plugin_kwargs = {}
    for option in plugin_options:
        if option.dest in config:
            plugin_kwargs[option.dest] = config[option.dest]
    return plugin_class(**plugin_kwargs)


def get_keystone_session():
    keystone_conf = CONF.keystone
    config = {}
    config['auth_url'] = keystone_conf.auth_url
    config['username'] = keystone_conf.admin_user
    config['password'] = keystone_conf.admin_password
    config['tenant_name'] = keystone_conf.admin_tenant_name

    if keystone_conf.auth_insecure:
        verify = False
    else:
        verify = keystone_conf.auth_ca_cert

    return Session(auth=_openstack_auth_from_config(**config), verify=verify)


def get_cinderclient(session=None, region=None):
    if not session:
        session = get_keystone_session()
    if not region:
        region = CONF.keystone['region']
    return cinder_client.Client(session=session,
                                region_name=region,
                                version=2)


def get_novaclient(session=None, region=None):
    if not session:
        session = get_keystone_session()
    if not region:
        region = CONF.keystone['region']
    return nova_client.Client(session=session,
                              region_name=region,
                              version=2)


def get_root_helper():
    return 'sudo fuxi-rootwrap %s' % CONF.rootwrap_config


def psutil_execute(*cmd, **kwargs):
    if 'run_as_root' not in kwargs:
        kwargs['run_as_root'] = True
    if 'root_helper' not in kwargs:
        kwargs['root_helper'] = get_root_helper()

    return processutils.execute(*cmd, **kwargs)
