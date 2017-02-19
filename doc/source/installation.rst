============
Installation
============

Prerequisites
-------------

* Install possibly required package for deploying Fuxi or running `fuxi-server`.

Ubuntu

::

    $ sudo apt-get update
    $ sudo apt-get install python-dev git libffi-dev libssl-dev gcc
    $ sudo apt-get install open-iscsi  # Install when using iSCSI client to connect remote volume
    $ sudo apt-get install sysfsutils  # Install when os_brick package and iSCSI client used

CentOS

::

    $ sudo yum -y install python-devel git gcc openssl-devel
    $ sudo yum install iscsi-initiator-utils # Install when using iSCSI client to connect remote volume
    $ sudo yum install sysfsutils  # Install when os_brick package and iSCSI client used

* Install requirements.

::

    $ curl https://bootstrap.pypa.io/get-pip.py | sudo python
    $ git clone https://github.com/openstack/fuxi.git
    $ cd fuxi
    $ sudo pip install -r requirements.txt


If `fuxi-server` run with non-root user, it is expected to enable `fuxi-server` to execute some Linux command without password interact.

Installing Fuxi
---------------

::

    $ sudo python setup.py install

Configuring Fuxi
----------------

After installing Fuxi, generate sample config, etc/fuxi.conf.sample, running the following:

::

    $ ./tools/generate_config_file_samples.sh

Rename and copy config file at required path:

::

    $ sudo cp etc/fuxi.conf.sample /etc/fuxi/fuxi.conf

Then edit it.

* Default section

::

    [DEFAULT]
    my_ip = MY_IP # The IP of host that Fuxi deployed on
    volume_providers = cinder # The enable volume provider for Fuxi

* Cinder section

::

    [cinder]
    region_name = REGION_NAME  # Region name of this node. This is used when picking the URL in the service catalog.
    auth_url = AUTH_URL # For example, it can be http://127.0.0.1:35357/v3/
    username = ADMIN_USER
    user_domain_name = Default
    password = ADMIN_PASSWORD
    project_name = service
    project_domain_name = Default
    auth_type = password
    volume_connector = VOLUME_CONNECTOR # The way to connect to volume. For Cinder, this could chose from `[openstack, osbrick]`
    fstype = ext4 # Default filesystem type to format, if not provided from request

* Nova section

::

    [nova]
    region_name = REGION_NAME  # Region name of this node. This is used when picking the URL in the service catalog.
    auth_url = AUTH_URL # For example, it can be http://127.0.0.1:35357/v3/
    username = ADMIN_USER
    user_domain_name = Default
    password = ADMIN_PASSWORD
    project_name = service
    project_domain_name = Default
    auth_type = password

Running Fuxi
------------
Fuxi could run with root user permission or non-root use permission. In order to make `fuxi-server` working normally, some extra config is inevitable.

For root user, when iSCSI client is used

::

    $ ln -s /lib/udev/scsi_id /usr/local/bin

For non-root user

::

    $ echo "fuxi ALL=(root) NOPASSWD: /usr/local/bin/fuxi-rootwrap /etc/fuxi/rootwrap.conf *" | sudo tee /etc/sudoers.d/fuxi-rootwrap

Here user `fuxi` should be changed to the user run `fuxi-server` on your host.

Start `fuxi-server`
::

    $ fuxi-server --config-file /etc/fuxi/fuxi.conf

Testing Fuxi
------------

::

    $ docker volume create --driver fuxi --name test_vol -o size=1 -o fstype=ext4 -o multiattach=true
    test_vol
    $ docker volume ls
    DRIVER              VOLUME NAME
    fuxi                test_vol
