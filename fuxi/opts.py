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

import fuxi.common.config


_fuxi_opts = [
    (None, list(itertools.chain(
        fuxi.common.config.default_opts))),
    ('keystone', fuxi.common.config.keystone_opts),
    ('cinder', fuxi.common.config.cinder_opts),
]


def list_fuxi_opts():
    return [('DEFAULT', itertools.chain(fuxi.common.config.default_opts,)),
            ('keystone', itertools.chain(fuxi.common.config.keystone_opts,)),
            ('cinder', itertools.chain(fuxi.common.config.cinder_opts,)), ]
