*** Settings ***
Documentation    Integration tests for building and verifying a debhello quilt-format Debian package.
...    The package is built with packtly-builder.
Library     OperatingSystem
Library     Process
Resource    ../keywords/git.resource
Resource    ../keywords/gpg.resource
Resource    ../keywords/aptly.resource
Resource    ../keywords/utils.resource

Suite Setup       Prepare Test Environment
Suite Teardown    Cleanup Test Environment


*** Variables ***
${FIXTURES_DIR}                 ${CURDIR}/../../fixtures
${DEBHELLO_DIR}                 ${FIXTURES_DIR}/debhello-quilt
${CONTAINER_IMAGE}              packtly-builder:latest
${WORKSPACE}                    ${TEMPDIR}/debhello-aptly-build
${KEYS_DIR}                     ${WORKSPACE}/keys
${PACKTLY_CREDENTIALS}          ${WORKSPACE}/aptly-credentials
${PACKTLY_GPG_KEY_SECRET}       packtly_gpg_private_key
${PACKTLY_GPG_PASS_SECRET}      packtly_gpg_passphrase
${PACKTLY_DATA_VOLUME}          robot_debhello_aptly_data
${PACKTLY_USER}                 admin
${PACKTLY_PASSWORD}             password
${PACKTLY_COMPOSE_FILE}         ${CURDIR}/packtly-infra.compose.yml
${PACKTLY_COMPOSE_PROJECT}      robot-debhello-aptly
${PACKTLY_NETWORK}              robot_debhello_aptly_net
&{PACKTLY_REPO}                 dist=trixie-apollo
...                             component=main
...                             description=Debhello Aptly test repo
...                             name=trixie-apollo-main
${TEST_CONTAINER}               robot-debhello-install


*** Test Cases ***
Debhello Quilt Build
    [Documentation]    Test building debhello package with packtly-builder
    [Tags]    build
    Run Debhello Quilt Build

Packtly Infra Repository Is Accessible
    [Documentation]    Verify the Packtly Apt repository is accessible from a Debian container.
    [Tags]    install
    Start Debian Test Container
    Import Repository Key
    Configure Debian Apt Repository

Install Binary Package
    [Documentation]    Verify the debhello package can be installed from the Packtly Apt repository.
    [Tags]    install
    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    apt-get install -y debhello

    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    dpkg -s debhello

    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    hello

Download Source Package
    [Documentation]    Verify the debhello source package can be downloaded from the Packtly Apt repository.
    [Tags]    install
    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    apt-get source debhello


*** Keywords ***
Remove Generated GPG Secrets
    [Documentation]    Remove the Podman secrets created for this test suite.
    Remove Podman Secret
    ...    ${PACKTLY_GPG_KEY_SECRET}
    Remove Podman Secret
    ...    ${PACKTLY_GPG_PASS_SECRET}

Cleanup Packtly Infra Container
    [Documentation]    Stop the packtly infra container and remove its data volume.
    Stop Podman Compose Service
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    Remove Generated GPG Secrets
    Remove Packtly Data Volume
    ...    ${PACKTLY_DATA_VOLUME}

Cleanup Test Environment
    [Documentation]    Cleanup the temporary workspace after the debhello-aptly build test.
    Cleanup Packtly Infra Container
    Stop Debian Test Container
    IF    '${WORKSPACE}' != ''
        Remove Directory    ${WORKSPACE}    recursive=True
    END

Import Generated GPG Secrets
    [Documentation]    Import the generated GPG private key and passphrase as Podman secrets.
    Import Podman Secret
    ...    ${PACKTLY_GPG_KEY_SECRET}
    ...    ${KEYS_DIR}/private/repo_signing_private.key
    Import Podman Secret
    ...    ${PACKTLY_GPG_PASS_SECRET}
    ...    ${KEYS_DIR}/private/repo_signing_private_pass

Prepare Packtly Infra Container
    [Documentation]    Prepare the packtly infra container

    Cleanup Packtly Infra Container
    Prepare Packtly Key Material
    Prepare Packtly Data Volume
    Start And Configure Packtly Service

Prepare Packtly Key Material
    [Documentation]    Generate the signing key and import its private parts as Podman secrets.
    Generate GPG Keys    ${KEYS_DIR}    ${CONTAINER_IMAGE}
    Import Generated GPG Secrets

Prepare Packtly Data Volume
    [Documentation]    Populate a newly created Packtly data volume with public configuration.
    Create Packtly Data Volume
    ...    ${PACKTLY_DATA_VOLUME}
    Install Packtly Public Files
    ...    ${PACKTLY_DATA_VOLUME}
    ...    ${KEYS_DIR}/public/repo_signing.key
    Generate Packtly Htpasswd
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    ...    ${PACKTLY_USER}
    ...    ${PACKTLY_PASSWORD}
    Generate Aptly Credentials
    ...    ${PACKTLY_CREDENTIALS}
    ...    ${PACKTLY_USER}
    ...    ${PACKTLY_PASSWORD}

Start And Configure Packtly Service
    [Documentation]    Start Packtly and create its published Aptly repository.
    Start Podman Compose Service
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    Wait Until Packtly Service Ready
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    Import Packtly GPG Key
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    Create Packtly Repo
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    ...    ${PACKTLY_REPO}
    Publish Packtly Repos
    ...    ${PACKTLY_COMPOSE_FILE}
    ...    ${PACKTLY_COMPOSE_PROJECT}
    ...    ${PACKTLY_REPO}[name]

Prepare Test Environment
    [Documentation]    Prepare a temporary workspace for the debhello-aptly build test.
    Run Process    git    clean    -fdx    cwd=${FIXTURES_DIR}
    Create Directory    ${WORKSPACE}
    Create Directory    ${WORKSPACE}/logs
    Prepare Packtly Infra Container
    Copy Directory    ${DEBHELLO_DIR}    ${WORKSPACE}/debhello-quilt

Run Debhello Quilt Build
    [Documentation]    packtly-builder build of the debhello-quilt package inside a container.
    [Arguments]    ${dist}=${PACKTLY_REPO}[dist]
    ...    ${component}=${PACKTLY_REPO}[component]

    ${result}=    Run Process
    ...    podman    run    --rm
    ...    -v    ${WORKSPACE}:/workspace:Z
    ...    -v    ${KEYS_DIR}/public/repo_signing.key:/opt/keys/gpg/repo_signing.key:Z,ro
    ...    -v    ${KEYS_DIR}/private/repo_signing_private.key:/opt/keys/gpg/repo_signing_private.key:Z,ro
    ...    -v    ${KEYS_DIR}/private/repo_signing_private_pass:/opt/keys/gpg/repo_signing_private_pass:Z,ro
    ...    -v    ${PACKTLY_CREDENTIALS}:/run/secrets/aptly-credentials:Z,ro
    ...    -v    ${WORKSPACE}/logs:/logs:Z
    ...    -e    APTLYHOST\=http://packtly:80
    ...    --network    ${PACKTLY_NETWORK}
    ...    ${CONTAINER_IMAGE}
    ...    /workspace/debhello-quilt
    ...    --log-file    /logs/build.log
    ...    --dist    ${dist}
    ...    --component    ${component}
    ...    --build-mode    full
    ...    --upload

    Log File    ${WORKSPACE}/logs/build.log
    Copy File    ${WORKSPACE}/logs/build.log    ${CURDIR}/../results/debhello_aptly.log
    Should Be Equal As Integers    ${result.rc}    0
    ...    Build failed with rc ${result.rc}. See stdout/stderr and build.log above.

Start Debian Test Container
    [Documentation]    Start a Debian container for testing the installation of the debhello package
    [Tags]    install
    ${result}=    Run Process
    ...    podman    run    -d
    ...    --name    ${TEST_CONTAINER}
    ...    --network    ${PACKTLY_NETWORK}
    ...    debian:trixie
    ...    sleep    infinity
    Should Be Equal As Integers    ${result.rc}    0

Import Repository Key
    [Documentation]    Import the Packtly repository signing key into the Debian test container.
    [Tags]    install
    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    apt-get update && apt-get install -y gnupg wget dpkg-dev

    ${keyring_cmd}=    Catenate    SEPARATOR=${EMPTY}
    ...    wget -O- http://packtly:80/repo_signing.key
    ...    | gpg --dearmor
    ...    > /usr/share/keyrings/packtly-archive-keyring.gpg

    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    bash -c "${keyring_cmd}"

Configure Debian Apt Repository
    [Documentation]    Configure the Debian test container to use the Packtly Apt repository.
    [Tags]    install

    ${sources}=    Catenate    SEPARATOR=\n
    ...    Types: deb deb-src
    ...    URIs: http://packtly:80
    ...    Suites: ${PACKTLY_REPO}[dist]
    ...    Components: ${PACKTLY_REPO}[component]
    ...    Signed-By: /usr/share/keyrings/packtly-archive-keyring.gpg

    ${cmd}=    Catenate    SEPARATOR=${EMPTY}
    ...    cat <<'EOF' > /etc/apt/sources.list.d/packtly.sources
    ...    \n${sources}
    ...    \nEOF

    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    bash -c "${cmd}"

    Execute In Test Container
    ...    ${TEST_CONTAINER}
    ...    apt-get update

Stop Debian Test Container
    [Documentation]    Stop and remove the Debian test container.
    [Tags]    install
    Run Process
    ...    podman    rm    -f    ${TEST_CONTAINER}
