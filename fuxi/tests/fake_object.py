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

import copy

DEFAULT_VOLUME_ID = 'efd46583-4bf7-40d5-a027-2ee3dbe74f56'
DEFAULT_VOLUME_NAME = 'fake_vol'

base_cinder_volume = {
    'attachments': [],
    'availability_zone': u'nova',
    'id': DEFAULT_VOLUME_ID,
    'size': 15,
    'display_name': DEFAULT_VOLUME_NAME,
    'metadata': {
        u'readonly': u'False',
        u'volume_from': u'fuxi',
        u'fstype': u'ext4',
    },
    'status': u'available',
    'multiattach': u'false',
    'volume_type': u'lvmdriver-1',
}


class FakeCinderVolume(object):
    def __init__(self, **kwargs):
        if 'name' in kwargs:
            kwargs['display_name'] = kwargs.pop('name')
        volume = (copy.deepcopy(base_cinder_volume))
        volume.update(kwargs)

        for key, value in volume.items():
            setattr(self, key, value)

    def get_name(self):
        return self.display_name

    def set_name(self, name):
        self.display_name = name

    name = property(get_name, set_name)
