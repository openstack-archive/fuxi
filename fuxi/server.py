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

import logging
import sys

from fuxi import app
from fuxi.common import config
from fuxi import controllers

LOG = logging.getLogger(__name__)


def start():
    config.init(sys.argv[1:])
    port = config.CONF.fuxi_port

    controllers.init_app_conf()
    LOG.info("start server on port: %s" % port)
    app.run("0.0.0.0", port,
            debug=config.CONF.debug,
            threaded=config.CONF.threaded)
