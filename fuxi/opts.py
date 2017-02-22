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

__all__ = [
    'list_fuxi_opts',
]

import itertools

from fuxi.common import config


def list_fuxi_opts():
    return [
        ('DEFAULT', itertools.chain(config.default_opts,)),
        (config.keystone_group.name,
         itertools.chain(config.legacy_keystone_opts,)),
        (config.cinder_group.name,
         itertools.chain(config.cinder_opts, config.keystone_auth_opts)),
        (config.nova_group.name,
         itertools.chain(config.nova_opts, config.keystone_auth_opts,)),
        (config.manila_group.name,
         itertools.chain(config.manila_opts, config.keystone_auth_opts))
    ]
