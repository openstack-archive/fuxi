#!/usr/bin/env bash

set -ex

VENV=${1:-"fullstack"}

GATE_DEST=$BASE/new
DEVSTACK_PATH=$GATE_DEST/devstack

export DEVSTACK_LOCAL_CONFIG+=$'\n'"enable_plugin manila git://git.openstack.org/openstack/manila"

$BASE/new/devstack-gate/devstack-vm-gate.sh
