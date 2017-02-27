#!/usr/bin/env bash

set -xe

FUXI_DIR="$BASE/new/fuxi"
TEMPEST_DIR="$BASE/new/tempest"
SCRIPTS_DIR="/usr/os-testr-env/bin/"

venv=${1:-"fullstack"}

function generate_test_logs {
    local path="$1"
    # Compress all $path/*.txt files and move the directories holding those
    # files to /opt/stack/logs. Files with .log suffix have their
    # suffix changed to .txt (so browsers will know to open the compressed
    # files and not download them).
    if [[ -d "$path" ]] ; then
        sudo find $path -iname "*.log" -type f -exec mv {} {}.txt \; -exec gzip -9 {}.txt \;
        sudo mv $path/* /opt/stack/logs/
    fi
}

function generate_testr_results {
    # Give job user rights to access tox logs
    sudo -H -u $owner chmod o+rw .
    sudo -H -u $owner chmod o+rw -R .testrepository
    if [[ -f ".testrepository/0" ]] ; then
        .tox/$venv/bin/subunit-1to2 < .testrepository/0 > ./testrepository.subunit
        $SCRIPTS_DIR/subunit2html ./testrepository.subunit testr_results.html
        gzip -9 ./testrepository.subunit
        gzip -9 ./testr_results.html
        sudo mv ./*.gz /opt/stack/logs/
    fi

    if [[ "$venv" == fullstack* ]] ; then
        generate_test_logs "/tmp/${venv}-logs"
    fi
}

owner=stack


# Set owner permissions according to job's requirements.
cd $FUXI_DIR
sudo chown -R $owner:stack $FUXI_DIR

echo "env before"
env | grep OS

# Get admin credentials
pushd ../devstack
source openrc fuxi service
popd

echo "env after"
env | grep OS

# Run tests
echo "Running Fuxi $venv fullstack tests"
set +e
sudo -H -E -u $owner env | grep OS
sudo -H -E -u $owner tox -e $venv
testr_exit_code=$?
set -e

# Collect and parse results
generate_testr_results
exit $testr_exit_code
