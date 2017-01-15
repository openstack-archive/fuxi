==========================
Run fullstack test locally
==========================

This is a guide for developers who want to run fullstack tests in their local
machine.

Prerequisite
============

You need to deploy Fuxi in a devstack environment.

Clone devstack::

    # Create a root directory for devstack if needed
    sudo mkdir -p /opt/stack
    sudo chown $USER /opt/stack

    git clone https://git.openstack.org/openstack-dev/devstack /opt/stack/devstack

We will run devstack with minimal local.conf settings required. You can use the
sample local.conf as a quick-start::

    git clone https://git.openstack.org/openstack/fuxi /opt/stack/fuxi
    cp /opt/stack/fuxi/devstack/local.config.sample /opt/stack/devstack

Run devstack::

    cd /opt/stack/devstack
    ./stack.sh

**NOTE:** This will take a while to setup the dev environment.

Preparation
===========

Navigate to fuxi directory::

    cd /opt/stack/fuxi

Source the credential of 'fuxi' user::

    source /opt/stack/devstack/openrc fuxi service

Run the test
============

Run this command::

    tox -efullstack