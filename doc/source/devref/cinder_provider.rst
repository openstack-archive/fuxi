..
      Copyright 2014 Mirantis Inc.
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Cinder provider
===============

Manila volume provider enable Fuxi create share from OpenStack Cinder and
support it as a volume for Docker to use.

Cinder provider configuration setttings
---------------------------------------

The following parameters in `cinder` group need to be set:

- `region_name` = <used to pick the URL from the service catalog>
- `volume_connector` = <the way to connect or disconect volume. default
     `osbrick`, only could chose from [osbrick, openstack]>
- `fstype` = <the filesystem type for formatting connected block device.
     default `ext4`>
- `multiattach` = <the volume is enabled to attached to multi-host.
     deafult `False`>

.. note::

    * If want to use keystone v3, please set authtoken configuration in group
    `cinder` or other group with `auth_section` marking it.

    * `multiattach` must be setting properly according to the enabled volume
    driver backends in Cinder.


Supported connectors
--------------------
- osbrick:   fuxi.connector.osbrickconnector.CinderConnector
- openstack: fuxi.connector.cloudconnector.openstack.CinderConnector

Connector osbrick
-----------------
osbrick connector uses OpenStack library package `os-brick`_ to manage the
connection with Cinder volume.
With this connector, `fuxi-server` could run in betemaral or VM normally.

Requirements
~~~~~~~~~~~~
- Install related client for connecting Cinder volume.
  eg: open-iscsi, nfs-common.
- When iSCSI client used and `fuxi-server` is running in root user, must make
  a link for executable file `ln -s /lib/udev/scsi_id`
  ::

    ln -s /lib/udev/scsi_id /usr/local/bin


Connector openstack
-------------------

This connector could be only running in Nova instance, because this connector
connect or disconnect volume with OpenStack Nova API.

Using
-----

The example for creating volume from Cinder with Docker volume command:

::

  docker volume create --driver fuxi --name <vol_name>
      --opts size=1
      --opts fstype=ext4
      --opts multiattach=true

Use existing Cinder volume:

::

  docker volume create --driver fuxi --name test_vol
      --opts size=1
      --opts volume_id=<volume_id>

.. _os-brick: https://github.com/openstack/os-brick
