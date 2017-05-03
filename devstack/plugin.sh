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

    (cd $FUXI_HOME && exec ./tools/generate_config_file_samples.sh)

    cp $FUXI_HOME/etc/fuxi.conf.sample $FUXI_CONFIG

    if is_service_enabled fuxi; then
        configure_auth_token_middleware $FUXI_CONFIG fuxi \
            $FUXI_AUTH_CACHE_DIR cinder
        configure_auth_token_middleware $FUXI_CONFIG fuxi \
            $FUXI_AUTH_CACHE_DIR manila

        iniset $FUXI_CONFIG DEFAULT fuxi_port 7879
        iniset $FUXI_CONFIG DEFAULT my_ip $HOST_IP
        iniset $FUXI_CONFIG DEFAULT volume_providers $FUXI_VOLUME_PROVIDERS
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
        pgrep -x "etcd" >/dev/null || run_process etcd-server "$DEST/etcd/etcd-$ETCD_VERSION-linux-amd64/etcd --data-dir $DEST/etcd/db.etcd --advertise-client-urls http://0.0.0.0:$FUXI_ETCD_PORT  --listen-client-urls http://0.0.0.0:$FUXI_ETCD_PORT"

        # In case iSCSI client is used
        sudo ln -s /lib/udev/scsi_id /usr/local/bin || true

        if [[ "$USE_PYTHON3" = "True" ]]; then
            # Switch off glance->swift communication as swift fails under py3.x
            iniset /etc/glance/glance-api.conf glance_store default_store file
        fi

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        run_process fuxi "/usr/bin/sudo fuxi-server --config-file $FUXI_CONFIG"

    fi

    if [[ "$1" == "unstack" ]]; then
        stop_process fuxi-server
        stop_process etcd-server
        rm -rf $DEST/etcd/
    fi
fi

# Restore xtrace
$XTRACE
