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
import random
import requests
import socket
import string
import traceback

from fuxi.common import constants
from fuxi import exceptions
from fuxi.i18n import _LW, _LE

from cinderclient import client as cinder_client
from cinderclient import exceptions as cinder_exception
from keystoneauth1.session import Session
from keystoneclient.auth import get_plugin_class
from manilaclient import client as manila_client
from manilaclient.openstack.common.apiclient import exceptions \
    as manila_exception
from novaclient import client as nova_client
from novaclient import exceptions as nova_exception
from os_brick import exception as brick_exception
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
        inst_uuid = ''
        inst_uuid_count = 0
        dirs = os.listdir(cloud_init_conf)
        for uuid_dir in dirs:
            if uuidutils.is_uuid_like(uuid_dir):
                inst_uuid = uuid_dir
                inst_uuid_count += 1

        # If not or not only get on instance_uuid, then search
        # it from metadata server.
        if inst_uuid_count == 1:
            return inst_uuid
    except Exception:
        LOG.warning(_LW("Get instance_uuid from cloud-init failed"))

    try:
        resp = requests.get('http://169.254.169.254/openstack',
                            timeout=constants.CURL_MD_TIMEOUT)
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
                                timeout=constants.CURL_MD_TIMEOUT)
            metadata = resp.json()
            if metadata.get('uuid', None):
                return metadata['uuid']
        except Exception as e:
            LOG.warning(_LW("Get instance_uuid from metadata server {0} "
                            "failed. Error: {1}").format(metadata_url, e))
            continue

    raise exceptions.FuxiException("Instance UUID Not Found")


# Return all errors as JSON. From http://flask.pocoo.org/snippets/83/
def make_json_app(import_name, **kwargs):
    app = flask.Flask(import_name, **kwargs)

    @app.errorhandler(exceptions.FuxiException)
    @app.errorhandler(cinder_exception.ClientException)
    @app.errorhandler(nova_exception.ClientException)
    @app.errorhandler(manila_exception.ClientException)
    @app.errorhandler(processutils.ProcessExecutionError)
    @app.errorhandler(brick_exception.BrickException)
    def make_json_error(ex):
        app.logger.error(_LE("Unexpected error happened: %s"),
                         traceback.format_exc())
        response = flask.jsonify({"Err": str(ex)})
        response.status_code = w_exceptions.InternalServerError.code
        if isinstance(ex, w_exceptions.HTTPException):
            response.status_code = ex.code
        content_type = 'application/vnd.docker.plugins.v1+json; charset=utf-8'
        response.headers['Content-Type'] = content_type
        return response

    for code in w_exceptions.default_exceptions:
        app.register_error_handler(code, make_json_error)

    return app


def driver_dict_from_config(named_driver_config, *args, **kwargs):
    driver_registry = dict()

    for driver_str in named_driver_config:
        driver_type, _sep, driver = driver_str.partition('=')
        driver_class = importutils.import_class(driver)
        driver_registry[driver_type] = driver_class(*args, **kwargs)
    return driver_registry


def _openstack_auth_from_config(**config):
    if config.get('username') and config.get('password'):
        plugin_class = get_plugin_class('password')
    else:
        plugin_class = get_plugin_class('token')
    plugin_options = plugin_class.get_options()
    plugin_kwargs = {}
    for option in plugin_options:
        if option.dest in config:
            plugin_kwargs[option.dest] = config[option.dest]
    return plugin_class(**plugin_kwargs)


def get_keystone_session(**kwargs):
    keystone_conf = CONF.keystone
    config = {}
    config['auth_url'] = keystone_conf.auth_url
    config['username'] = keystone_conf.admin_user
    config['password'] = keystone_conf.admin_password
    config['tenant_name'] = keystone_conf.admin_tenant_name
    config['token'] = keystone_conf.admin_token
    config.update(kwargs)

    if keystone_conf.auth_insecure:
        verify = False
    else:
        verify = keystone_conf.auth_ca_cert

    return Session(auth=_openstack_auth_from_config(**config), verify=verify)


def get_cinderclient(session=None, region=None, **kwargs):
    if not session:
        session = get_keystone_session(**kwargs)
    if not region:
        region = CONF.keystone['region']
    return cinder_client.Client(session=session,
                                region_name=region,
                                version=2)


def get_novaclient(session=None, region=None, **kwargs):
    if not session:
        session = get_keystone_session(**kwargs)
    if not region:
        region = CONF.keystone['region']
    return nova_client.Client(session=session,
                              region_name=region,
                              version=2)


def get_manilaclient(session=None, region=None):
    if not session:
        session = get_keystone_session()
    if not region:
        region = CONF.keystone['region']
    return manila_client.Client(session=get_keystone_session(),
                                region_name=region,
                                client_version='2')


def get_root_helper():
    return 'sudo fuxi-rootwrap %s' % CONF.rootwrap_config


def execute(*cmd, **kwargs):
    if 'run_as_root' in kwargs and 'root_helper' not in kwargs:
        kwargs['root_helper'] = get_root_helper()

    return processutils.execute(*cmd, **kwargs)


def get_random_string(n=10):
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(n))


def wrap_check_authorized(f):
    """If token is expired, then build a new client, and try again.

    This method required the related object(cls) has method set_client().
    method set_client() is used to reset OpenStack *client.
    """
    def func(cls, *args, **kwargs):
        try:
            return f(cls, *args, **kwargs)
        except manila_exception.Unauthorized:
            cls.set_client()
            return f(cls, *args, **kwargs)
    return func
