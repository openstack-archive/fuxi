#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from kuryr.lib import config as kuryr_config
from kuryr.lib import opts as kuryr_opts
from oslo_config import cfg
from oslo_log import log as logging

from fuxi import i18n
from fuxi.version import version_info

_ = i18n._

default_opts = [
    cfg.StrOpt('my_ip',
               help=_('IP address of this machine.')),
    cfg.IntOpt('fuxi_port',
               default=7879,
               help=_('Port for fuxi volume driver server.')),
    cfg.StrOpt('volume_dir',
               default='/fuxi/data',
               help=_('At which the docker volume will create.')),
    cfg.ListOpt('volume_providers',
                help=_('Volume storage backends that provide volume for '
                       'Docker')),
    cfg.StrOpt('volume_from',
               default='fuxi',
               help=_('Setting label for volume.')),
    cfg.IntOpt('default_volume_size',
               default=1,
               help=_('Default size for volume.')),
    cfg.BoolOpt('threaded',
                default=True,
                help=_('Make this volume plugin run in multi-thread.')),
    cfg.StrOpt('rootwrap_config',
               default='/etc/fuxi/rootwrap.conf'),
]

legacy_keystone_opts = [
    cfg.StrOpt('region',
               default=os.environ.get('REGION'),
               help=_('The region that this machine belongs to.'),
               deprecated_for_removal=True),
    cfg.StrOpt('auth_url',
               default=os.environ.get('IDENTITY_URL'),
               help=_('The URL for accessing the identity service.'),
               deprecated_for_removal=True),
    cfg.StrOpt('admin_user',
               default=os.environ.get('SERVICE_USER'),
               help=_('The username to auth with the identity service.')),
    cfg.StrOpt('admin_tenant_name',
               default=os.environ.get('SERVICE_TENANT_NAME'),
               help=_('The tenant name to auth with the identity service.'),
               deprecated_for_removal=True),
    cfg.StrOpt('admin_password',
               default=os.environ.get('SERVICE_PASSWORD'),
               help=_('The password to auth with the identity service.'),
               deprecated_for_removal=True),
    cfg.StrOpt('admin_token',
               default=os.environ.get('SERVICE_TOKEN'),
               help=_('The admin token.'),
               deprecated_for_removal=True),
    cfg.StrOpt('auth_ca_cert',
               default=os.environ.get('SERVICE_CA_CERT'),
               help=_('The CA certification file.'),
               deprecated_for_removal=True),
    cfg.BoolOpt('auth_insecure',
                default=True,
                help=_("Turn off verification of the certificate for ssl."),
                deprecated_for_removal=True),
]

cinder_opts = [
    cfg.StrOpt('volume_connector',
               default='osbrick',
               help=_('Volume connector for attach volume to this server, '
                      'or detach volume from this server.')),
    cfg.StrOpt('availability_zone',
               default=None,
               help=_('AZ in which the current machine creates, '
                      'and volume is going to create.')),
    cfg.StrOpt('volume_type',
               default=None,
               help=_('Volume type to create volume.')),
    cfg.StrOpt('fstype',
               default='ext4',
               help=_('Default filesystem type for volume.')),
    cfg.BoolOpt('multiattach',
                default=False,
                help=_('Allow the volume to be attached to more than '
                       'one instance.'))
]


CONF = cfg.CONF
CONF.register_opts(default_opts)
CONF.register_opts(legacy_keystone_opts, group='keystone')
CONF.register_opts(cinder_opts, group='cinder')

CFG_GROUP = 'cinder'

# Settting options for Keystone.
kuryr_config.register_keystoneauth_opts(CONF, CFG_GROUP)
CONF.set_default('auth_type', default='password', group=CFG_GROUP)

keystone_auth_opts = kuryr_opts.get_keystoneauth_conf_options()

# Setting oslo.log options for logging.
logging.register_options(CONF)


def init(args, **kwargs):
    cfg.CONF(args=args, project='fuxi',
             version=version_info.release_string(), **kwargs)
