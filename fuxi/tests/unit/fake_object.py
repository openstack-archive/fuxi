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
    'availability_zone': 'nova',
    'id': DEFAULT_VOLUME_ID,
    'size': 15,
    'display_name': DEFAULT_VOLUME_NAME,
    'metadata': {
        'readonly': 'False',
        'volume_from': 'fuxi',
        'fstype': 'ext4',
    },
    'status': 'available',
    'multiattach': 'false',
    'volume_type': 'lvmdriver-1',
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


fake_share = {
    'id': DEFAULT_VOLUME_ID,
    'name': DEFAULT_VOLUME_NAME,
    'export_location': '192.168.0.1:/tmp/share',
    'share_proto': 'NFS'
}


class FakeManilaShare(object):
    def __init__(self, **kwargs):
        share = copy.deepcopy(fake_share)
        share.update(kwargs)
        for key, value in share.items():
            setattr(self, key, value)


fake_share_access = {
    'share_id': 'efd46583-4bf7-40d5-a027-2ee3dbe74f56',
    'access_type': 'ip',
    'access_to': '192.168.0.1',
    'access_level': 'rw'
}


class FakeShareAccess(object):
    def __init__(self, **kwargs):
        share_access = copy.deepcopy(fake_share_access)
        share_access.update(kwargs)
        for key, value in share_access.items():
            setattr(self, key, value)
