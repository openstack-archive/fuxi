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

from fuxi.tests.unit import fake_object

from cinderclient import exceptions as cinder_exception


class FakeCinderClient(object):
    class Volumes(object):
        def get(self, volume_id):
            return fake_object.FakeCinderVolume(id=volume_id)

        def list(self, search_opts={}):
            return [fake_object.FakeCinderVolume(name='fake-vol1')]

        def create(self, *args, **kwargs):
            return fake_object.FakeCinderVolume(**kwargs)

        def delete(self, volume_id):
            return

        def attach(self, volume, instance_uuid, mountpoint, host_name):
            if not instance_uuid and not host_name:
                raise cinder_exception.ClientException

            attachment = {u'server_id': instance_uuid,
                          u'attachment_id': u'123',
                          u'attached_at': u'2016-05-20T09:19:57.000000',
                          u'host_name': host_name,
                          u'device': None,
                          u'id': u'123'}

            volume.attachments.append(attachment)
            return volume

        def detach(self, volume_id, attachment_uuid):
            pass

        def initialize_connection(self, volume, connector):
            return {'data': {}}

        def reserve(self, volume):
            return

        def update(self, volume, **kwargs):
            for key, value in kwargs.items():
                if hasattr(volume, key):
                    setattr(volume, key, value)

        def set_metadata(self, volume, metadata):
            md = volume.metadata
            md.update(metadata)

        def __getattr__(self, item):
            return None

    def __init__(self):
        self.volumes = self.Volumes()


class FakeNovaClient(object):
    class Volumes(object):
        def create_server_volume(self, volume_id):
            pass

        def delete_server_volume(self, server_id, volume_id):
            return None

    def __init__(self):
        self.volumes = self.Volumes()


class FakeOSBrickConnector(object):
    def connect_volume(self, connection_properties):
        return {'path': 'fake-path'}

    def disconnect_volume(self, connection_properties, device_info):
        pass

    def get_volume_paths(self, connection_properties):
        return ['/fuxi/data/fake-vol']


class FakeManilaClient(object):
    class Shares(object):
        def get(self, share):
            try:
                return fake_object.FakeManilaShare(id=share.id)
            except AttributeError:
                return fake_object.FakeManilaShare(id=share)

        def create(self, *args, **kawrgs):
            pass

        def list(self):
            return []

        def allow(self, share, access_type, access, access_level):
            pass

        def deny(self, share, share_access_id):
            pass

        def access_list(self, share):
            return []

        def update(self, **kwargs):
            pass

        def update_all_metadata(self, share, metadata):
            share.metadata.update(**metadata)

    class ShareNetworks(object):
        def list(self):
            return []

        def create(self):
            pass

    def __init__(self):
        self.shares = self.Shares()
        self.share_networks = self.ShareNetworks()
