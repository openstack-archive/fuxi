#!/usr/bin/env bash

set -ex

VENV=${1:-"fullstack"}

GATE_DEST=$BASE/new
DEVSTACK_PATH=$GATE_DEST/devstack

export DEVSTACK_LOCAL_CONFIG+=$'\n'"enable_plugin manila git://git.openstack.org/openstack/manila"
export MANILA_DEFAULT_SHARE_TYPE_EXTRA_SPECS='snapshot_support=True create_share_from_snapshot_support=True revert_to_snapshot_support=True mount_snapshot_support=True'
export SHARE_DRIVER=manila.share.drivers.lvm.LVMShareDriver
export MANILA_OPTGROUP_generic1_driver_handles_share_servers=False

$BASE/new/devstack-gate/devstack-vm-gate.sh
