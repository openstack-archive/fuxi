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

VOLUME_FROM = 'volume_from'
DOCKER_VOLUME_NAME = 'docker_volume_name'

# Volume states
UNKNOWN = 'unknown'
NOT_ATTACH = 'not_attach'
ATTACH_TO_THIS = 'attach_to_this'
ATTACH_TO_OTHER = 'attach_to_other'

# If volume_provider is cinder, and if cinder volume is attached to this server
# by Nova, an link file will create under this directory to match attached
# volume. Of course, creating link file will decrease interact time
# with backend providers in some cases.
VOLUME_LINK_DIR = '/dev/disk/by-id/'

# Volume scanning interval
VOLUME_SCAN_TIME_DELAY = 0.3

# Timeout for destroying volume from backend provider
DESTROY_VOLUME_TIMEOUT = 300

# Timeout for monitoring volume status
MONITOR_STATE_TIMEOUT = 600

# Device scan interval
DEVICE_SCAN_TIME_DELAY = 0.3

# Timeout for scanning device
DEVICE_SCAN_TIMEOUT = 10

# Timeout for querying meta-data from localhost
CURL_MD_TIMEOUT = 10
