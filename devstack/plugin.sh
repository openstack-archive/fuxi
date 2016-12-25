#!/bin/bash
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set +o xtrace

ETCD_VERSION=v2.2.2

function install_etcd_data_store {

    if [ ! -f "$DEST/etcd/etcd-$ETCD_VERSION-linux-amd64/etcd" ]; then
        echo "Installing etcd server"
        mkdir $DEST/etcd
        wget https://github.com/coreos/etcd/releases/download/$ETCD_VERSION/etcd-$ETCD_VERSION-linux-amd64.tar.gz -O $DEST/etcd/etcd-$ETCD_VERSION-linux-amd64.tar.gz
        tar xzvf $DEST/etcd/etcd-$ETCD_VERSION-linux-amd64.tar.gz -C $DEST/etcd
    fi

    # Clean previous DB data
    rm -rf $DEST/etcd/db.etcd
}

function check_docker {
    if is_ubuntu; then
       dpkg -s docker-engine > /dev/null 2>&1
    else
       rpm -q docker-engine > /dev/null 2>&1 || rpm -q docker > /dev/null 2>&1
    fi
}

function create_fuxi_account {
    if is_service_enabled fuxi; then
        create_service_user "fuxi" "admin"
        get_or_create_service "fuxi" "fuxi" "Fuxi Service"
    fi
}

function configure_fuxi {
    sudo install -d -o $STACK_USER $FUXI_CONFIG_DIR

    (cd $FUXI_HOME && tox -egenconfig)

    cp $FUXI_HOME/etc/fuxi.conf.sample $FUXI_CONFIG

    if is_service_enabled fuxi; then
        configure_auth_token_middleware $FUXI_CONFIG fuxi \
            $FUXI_AUTH_CACHE_DIR cinder

        iniset $FUXI_CONFIG DEFAULT fuxi_port 7879
        iniset $FUXI_CONFIG DEFAULT my_ip $HOST_IP
        iniset $FUXI_CONFIG DEFAULT volume_providers cinder
        iniset $FUXI_CONFIG DEFAULT volume_from fuxi
        iniset $FUXI_CONFIG DEFAULT default_volume_size 1
        iniset $FUXI_CONFIG DEFAULT volume_dir /fuxi/data
        iniset $FUXI_CONFIG DEFAULT threaded true
        iniset $FUXI_CONFIG DEFAULT debug True

        iniset $FUXI_CONFIG cinder volume_connector osbrick
        iniset $FUXI_CONFIG cinder multiattach false
        iniset $FUXI_CONFIG cinder fstype ext4
    fi
}


# main loop
if is_service_enabled fuxi; then

    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        if use_library_from_git "kuryr"; then
            git_clone_by_name "kuryr"
            setup_dev_lib "kuryr"
        fi
        install_etcd_data_store
        setup_develop $FUXI_HOME

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then

        if [[ ! -d "${FUXI_ACTIVATOR_DIR}" ]]; then
            echo -n "${FUXI_ACTIVATOR_DIR} directory is missing. Creating it... "
            sudo mkdir -p ${FUXI_ACTIVATOR_DIR}
            echo "Done"
        fi

        if [[ ! -f "${FUXI_ACTIVATOR}" ]]; then
             echo -n "${FUXI_ACTIVATOR} is missing. Copying the default one... "
             sudo cp ${FUXI_DEFAULT_ACTIVATOR} ${FUXI_ACTIVATOR}
             echo "Done"
        fi

        create_fuxi_account
        configure_fuxi

        # Run etcd first
        run_process etcd-server "$DEST/etcd/etcd-$ETCD_VERSION-linux-amd64/etcd --data-dir $DEST/etcd/db.etcd --advertise-client-urls http://0.0.0.0:$FUXI_ETCD_PORT  --listen-client-urls http://0.0.0.0:$FUXI_ETCD_PORT"

        # FIXME(mestery): By default, Ubuntu ships with /bin/sh pointing to
        # the dash shell.
        # ..
        # ..
        # The dots above represent a pause as you pick yourself up off the
        # floor. This means the latest version of "install_docker.sh" to load
        # docker fails because dash can't interpret some of it's bash-specific
        # things. It's a bug in install_docker.sh that it relies on those and
        # uses a shebang of /bin/sh, but that doesn't help us if we want to run
        # docker and specifically Fuxi. So, this works around that.
        sudo update-alternatives --install /bin/sh sh /bin/bash 100

        # Install docker only if it's not already installed. The following checks
        # whether the docker-engine package is already installed, as this is the
        # most common way for installing docker from binaries. In case it's been
        # manually installed, the install_docker.sh script will prompt a warning
        # if another docker executable is found
        check_docker || {
            wget http://get.docker.com -O install_docker.sh
            sudo chmod 777 install_docker.sh
            sudo sh install_docker.sh
            sudo rm install_docker.sh
        }

        # After an ./unstack it will be stopped. So it is ok if it returns exit-code == 1
        sudo service docker stop || true

        run_process docker-engine "sudo /usr/bin/docker daemon -H unix://$FUXI_DOCKER_ENGINE_SOCKET_FILE -H tcp://0.0.0.0:$FUXI_DOCKER_ENGINE_PORT --cluster-store etcd://localhost:$FUXI_ETCD_PORT"

        # We put the stack user as owner of the socket so we do not need to
        # run the Docker commands with sudo when developing.
        echo -n "Waiting for Docker to create its socket file"
        while [ ! -e "$FUXI_DOCKER_ENGINE_SOCKET_FILE" ]; do
            echo -n "."
            sleep 1
        done
        echo ""
        sudo chown "$STACK_USER":docker "$FUXI_DOCKER_ENGINE_SOCKET_FILE"

        # In case iSCSI client is used
        sudo ln -s /lib/udev/scsi_id /usr/local/bin || true

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        run_process fuxi "sudo fuxi-server --config-file $FUXI_CONFIG"

    fi

    if [[ "$1" == "unstack" ]]; then
        stop_process fuxi-server
        stop_process etcd-server
        rm -rf $DEST/etcd/
        stop_process docker-engine
        # Stop process does not handle well Docker 1.12+ new multi process
        # split and doesn't kill them all. Let's leverage Docker's own pidfile
        sudo kill -s SIGTERM "$(cat /var/run/docker.pid)"
    fi
fi

# Restore xtrace
$XTRACE
