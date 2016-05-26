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


class FuxiException(Exception):
    """Default Kuryr exception"""


class TimeoutException(FuxiException):
    """A timeout on waiting for volume to reach destination end state."""


class UnexpectedStateException(FuxiException):
    """Unexpected volume state appeared"""


class LoopExceeded(FuxiException):
    """Raised when ``loop_until`` looped too many times."""


class NotFound(FuxiException):
    """The resource could not be found"""


class TooManyResources(FuxiException):
    """Find too many resources."""


class InvalidInput(FuxiException):
    """Request data is invalidate"""


class NotMatchedState(FuxiException):
    """Current state not match to expected state"""
    message = "Current state not match to expected state."
