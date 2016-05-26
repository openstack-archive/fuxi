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

from fuxi.tests import fake_volume

from cinderclient import exceptions as cinder_exception


class FakeCinderClient(object):
    class Volumes(object):
        def get(self, volume_id):
            return fake_volume.FakeCinderVolume(id=volume_id)

        def list(self, search_opts={}):
            return [fake_volume.FakeCinderVolume(name='fake-vol1')]

        def create(self, *args, **kwargs):
            return fake_volume.FakeCinderVolume(**kwargs)

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

        def __getattr__(self, item):
            return None

    def __init__(self):
        self.volumes = self.Volumes()
