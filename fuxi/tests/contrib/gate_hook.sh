#!/usr/bin/env bash

set -ex

VENV=${1:-"fullstack"}

GATE_DEST=$BASE/new
DEVSTACK_PATH=$GATE_DEST/devstack

export DEVSTACK_LOCAL_CONFIG="enable_plugin fuxi https://git.openstack.org/openstack/fuxi"

$BASE/new/devstack-gate/devstack-vm-gate.sh
