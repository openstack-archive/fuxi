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

Manila provider
===============

Manila volume provider enable Fuxi create share from OpenStack Manila and
support it as a volume for Docker to use.

Requirements
------------
- Install the related client according the driver backends that Manila
  used for mounting the remote filesystem.


Manila provider configuration settings
--------------------------------------

The following parameters in `manila` group need to be set:

- `region_name` = <used to pick the URL from the service catalog>

The following configuration parameters are options:

- `volume_connector` = osbrick
- `share_proto` = <default share protocol used to grant access>
- `proto_access_type_map` = <the mapping of protocol access
     that manila enabled>
- `access_to_for_cert` = <the value of key `access_to` when Manila use
     `access_type` `CERT` to allow access for visitors>

.. note::

   If want to use keystone v3, please set authtoken configuration in group
   `manila` or other group with `auth_section` marking it.


Using
-----

Set `volume_providers = manila` in group `DEFAULT` to use Manila volume
provider.

For different backends that manila enabled, we need to provide different
parameter to create volume(share) from Manila.

The following are some examples.

- If use `generic` driver in Manila, `share_network` should be provided;

::

  docker volume create --driver fuxi --name <vol_name>
      --opts share_network=<share_network_id>

- If use `glusterfs` driver in Manila, `share_type` should be provided;

::

  docker volume create --driver fuxi --name <volume_name>
      --opts share_type=<share_type_id>

- If use `glusterfs_native` driver in Manila, `share_type` and `share_proto`
    need be provided;

::

  docker volume create --driver fuxi --name <vol_name>
      --opts share_type=<share_type_id>
      --opts share_proto=glusterfs


Using existing Manila share:

::

  docker volume create --driver fuxi --name <vol_name>
      --opts volume_id=<share_id>

.. note::

   The parameter `--opts volume_provider=manila` is needed, if you want
   use Manila volume provider when multi volume providers are enabled and
   `manila` is not the first one.

References
----------

* `Manila share features support mapping`_

.. _Manila share features support mapping: https://docs.openstack.org/developer/manila/devref/share_back_ends_feature_support_mapping.html
